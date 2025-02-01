from typing import Any, Union, List, Dict
from agent.LLM.llm_instance import create_llm_instance
import json
import pandas as pd
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

async def format_converter(input_text: str, target_type: str, output_parameters: dict) -> Union[List[Any], Dict[str, Any], bool, str, float, pd.DataFrame]:
    """Convert the input text to the desired format using GPT-4"""

    # TODO: This is a temporary solution for handling link lists
    # Should be refactored to handle more general cases and different response types
    def is_link_response(input_data: Union[str, Dict, List]) -> bool:
        """Check if the input contains link-related data"""
        try:
            # Handle string input
            if isinstance(input_data, str):
                try:
                    data = json.loads(input_data)
                except json.JSONDecodeError:
                    return False
            else:
                data = input_data
            
            # Check dictionary
            if isinstance(data, dict):
                return any('link' in key.lower() for key in data.keys())
            # Check list of dictionaries
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                return any('link' in key.lower() for item in data for key in item.keys())
            
            return False
            
        except Exception as e:
            logger.error(f"Error in is_link_response: {e}")
            return False
    
    def process_link_response(input_data: Union[str, Dict, List]) -> Union[List[str], Dict[str, Any]]:
        """Process response containing links, removing None values from lists"""
        try:
            # Handle string input
            if isinstance(input_data, str):
                try:
                    data = json.loads(input_data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse JSON string")
                    return input_data
            else:
                data = input_data
            
            # Handle dictionary
            if isinstance(data, dict):
                for key in data:
                    if 'link' in key.lower() and isinstance(data[key], list):
                        # Remove None and empty values from list
                        data[key] = [x for x in data[key] if x is not None and x != ""]
                        logger.debug(f"Processed link list for key {key}, new length: {len(data[key])}")
                return data
            
            # Handle list of dictionaries
            elif isinstance(data, list):
                if data and isinstance(data[0], dict):
                    # Process each dictionary in the list
                    processed_list = []
                    for item in data:
                        processed_item = {}
                        for key, value in item.items():
                            if 'link' in key.lower() and isinstance(value, list):
                                processed_item[key] = [x for x in value if x is not None and x != ""]
                                return processed_item
                    
                else:
                    # Handle simple list
                    return [x for x in data if x is not None and x != ""]
                
            return data
            
        except Exception as e:
            logger.error(f"Error processing link response: {e}")
            return input_data
    
    prompts = {
        "text": """Summarize or format the following text into a clear, concise response.
                  Return only the final text without any additional formatting.
                  Text to process: {text}
                  Target Output parameters: {output_parameters}""",
        "list": """Convert the following text into a list of items. Return only a valid JSON array.
                  Example: ["item1", "item2", "item3"]
                  Text to convert: {text}
                  Target Output parameters: {output_parameters}""",
        "json": """Convert the following text into a structured JSON dictionary object with relevant fields.
                  Return only valid JSON.
                  Text to structure: {text}
                  Target Output parameters: {output_parameters}""",
        "number": """Extract or convert the numerical value from the following text.
                    Return only the number without any units or additional text.
                    Text to process: {text}
                    Target Output parameters: {output_parameters}""",
        "boolean": """Based on the following text, determine if it indicates true/yes or false/no.
                     Return only the word 'true' or 'false'.
                     Text to analyze: {text}
                     Target Output parameters: {output_parameters}""",
        "table": """Convert the following text into a table format using markdown table syntax.
                   Include headers and proper column alignment.
                   Text to tabulate: {text}
                   Target Output parameters: {output_parameters}"""
    }
    
    if target_type not in prompts:
        raise ValueError(f"Unsupported target type: {target_type}")
        
    prompt = prompts[target_type].format(text=input_text, output_parameters=output_parameters)
    system_prompt = "You are a helpful assistant that converts input text into the desired format following the target output parameters requirements. For example, if the target output parameters is {'blog_post_links': []} and the target type is list, the output should be list of blog post links."
    
    try:
        if target_type == "list" and is_link_response(input_text):
            logger.info("Detected link response, applying special processing")
            processed_data = process_link_response(input_text)
            if isinstance(processed_data, dict):
                # Extract the first list value found in the dict
                for key in processed_data:
                    if isinstance(processed_data[key], list):
                        logger.info(f"Returning list from key: {key}")
                        return processed_data[key]
            return processed_data if isinstance(processed_data, list) else []
        llm = create_llm_instance("gpt-4o")
        response, _ = await llm.request(messages=[{"role": "system", "content": system_prompt},{"role": "user", "content": prompt}])
        response = response.strip()
        
        if target_type == "list":
            try:
                if not response.startswith('['):
                    response = response[response.find('['):]
                if not response.endswith(']'):
                    response = response[:response.rfind(']')+1]
                return json.loads(response)
            except:
                return []
                
        elif target_type == "json":
            try:
                return json.loads(response)
            except:
                return {}
                
        elif target_type == "number":
            try:
                return float(response.replace(',', ''))
            except:
                return 0.0
                
        elif target_type == "boolean":
            return response.lower() == "true"
            
        elif target_type == "table":
            try:
                if response.startswith('['):
                    # Handle JSON array format
                    data = json.loads(response)
                    return pd.DataFrame(data)
                else:
                    # Handle markdown table format
                    return pd.read_csv(pd.StringIO(response), sep='|', skipinitialspace=True)
            except:
                return pd.DataFrame()
                
        else:  # text type
            return response
            
    except Exception as e:
        logger.error(f"Format conversion error: {str(e)}")
        # Return type-appropriate default values on error
        if target_type == "list":
            return []
        elif target_type == "json":
            return {}
        elif target_type == "number":
            return 0.0
        elif target_type == "boolean":
            return False
        elif target_type == "table":
            return pd.DataFrame()
        else:
            return input_text 

async def planning_response_converter(input_text: str) -> dict:
    """Convert unstructured planning response text into the required JSON format"""
    
    prompt = """Convert the following planning response into a valid JSON object with this exact structure:
    {
        "thought": "Brief thought process",
        "action": "action_name",
        "action_input": "input_value",
        "element_id": 0,
        "description": "Brief description"
    }

    For responses about collecting links, format them like this:
    {
        "thought": "Need to collect product links for verification",
        "action": "get_final_answer",
        "action_input": {
            "related_links": [id1, id2, id3]
        },
        "element_id": 0,
        "description": "Extracting product links for verification"
    }

    Extract link IDs from text like '[123] link' by taking just the number.
    Return only the valid JSON object.

    Text to convert: {text}"""
    
    try:
        llm = create_llm_instance("gpt-4o")
        response, _ = await llm.request(messages=[{"role": "user", "content": prompt.format(text=input_text)}])
        response = response.strip()
        
        # Extract JSON object if embedded in other text
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            response = response[start:end]
            
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback default response
            return {
                "thought": "Extracting product information",
                "action": "get_final_answer",
                "action_input": {"related_links": []},
                "element_id": 0,
                "description": "Converting product information to structured format"
            }
            
    except Exception as e:
        logger.error(f"Planning response conversion error: {str(e)}")
        # Return default structure on error
        return {
            "thought": "Extracting product information",
            "action": "get_final_answer",
            "action_input": {"related_links": []},
            "element_id": 0,
            "description": "Converting product information to structured format"
        } 

async def validate_and_replan_links(
    text_content: Union[str, List, Dict], 
    observation: str, 
    task_name: str, 
    output_parameters: dict = None,
    response_type: str = None,
    final_url: str = None
) -> Union[str, List, Dict]:
    """
    Validates and replans links in the content, maintaining the original output format.
    
    Args:
        text_content: Original content to validate
        observation: Current page observation
        task_name: Name of the current task
        output_parameters: Parameters defining expected output format
        response_type: Type of response expected
        final_url: Final URL of the page
    """
    def contains_link_pattern(content: str) -> bool:
        link_patterns = [
            r'https?://',
            r'www\.',
            r'\.com',
            r'\.org',
            r'\.net',
            r'/[a-zA-Z0-9\-_/]+',
            r'href=',
            r'<a',
            r'link to'
        ]
        return any(re.search(pattern, content, re.IGNORECASE) for pattern in link_patterns)

    def check_content(content) -> bool:
        if isinstance(content, str):
            return contains_link_pattern(content)
        elif isinstance(content, list):
            return any(check_content(item) for item in content)
        elif isinstance(content, dict):
            return any(check_content(value) for value in content.values())
        return False

    def is_allowed_link(link: str) -> bool:
        """Check if the link is from output_parameters or matches final_url domain"""
        if not link:
            return False
            
        # Check if link is in output_parameters
        if task_name:
            if link in task_name:
                return True
                
        # Check if link matches final_url domain
        if final_url:
            try:
                link_domain = urlparse(link).netloc
                final_domain = urlparse(final_url).netloc
                return link_domain == final_domain
            except:
                pass
        return False

    # If no links found, return original content
    if not check_content(text_content):
        return text_content

    system_prompt = """You are a web automation assistant. When processing links:
    1. For links that you obtain from the task name or final page URL domain:
       - Keep them as direct URLs in the output
    2. For other links:
       - Replace them with element IDs from the observation
    3. Maintain the exact same output structure as the Previous response
    4. Never generate or guess links or IDs
    """

    user_prompt = f"""Based on the current page observation and requirements:
    
    Task: {task_name}
    Required Output Format: {output_parameters}
    Response Type: {response_type}
    Final URL: {final_url}
    
    Current Page Content:
    {observation}
    
    Previous response: {text_content}
    
    Please provide a new response that:
    1. Maintains the exact same structure as the Previous response
    2. Keeps direct URLs only if they are from the task name or final URL
    3. Uses element IDs for all other links.(IMPORTANT!)
    """

    try:
        llm = create_llm_instance("gpt-4o")
        response, _ = await llm.request(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        
        # Parse and validate response based on type
        if response_type == "list":
            try:
                result = json.loads(response)
                return result if isinstance(result, list) else []
            except:
                return []
        elif response_type == "dict":
            try:
                result = json.loads(response)
                return result if isinstance(result, dict) else {}
            except:
                return {}
        else:
            return response.strip()
            
    except Exception as e:
        logger.error(f"Error in validate_and_replan_links: {str(e)}")
        return text_content 