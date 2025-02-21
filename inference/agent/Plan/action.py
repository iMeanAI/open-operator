import re
from typing import Tuple, Any, List

import json5
import json

import traceback
from agent.Prompt import *
from ..Utils import *


class ResponseError(Exception):
    """Custom response error type"""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ActionParser():
    def __init__(self):
        pass

    # Extract Thought and Action from the results returned by LLM,
    # return thought (str) and action (dict), where action has four fields: action, element_id, action_input, description
    async def extract_thought_and_action(self, response: str, mode: str) -> Tuple[dict, dict]:
        result_action = None
        
        # First attempt: Try parsing with regex
        # Try to extract content between markdown code blocks first
        code_block = re.findall("```(.*?)```", response, re.S)
        if code_block:
            result_action = self.parse_action(code_block[0])
        
        # If no code block found or parsing failed, try parsing the whole response
        if not result_action:
            try:
                result_action = self.parse_action(response)
            except:
                pass
            
        # If that fails, try regex-based parsing
        if not result_action:
            result_action = self.parse_action_with_re(response, mode)
                
        # Second attempt: Try using converter + regex if all regex methods failed
        if not result_action:
            try:
                # Convert the response to proper format
                converted_response = await planning_response_converter(response)
                if converted_response:
                    result_action = converted_response
                else:
                    # Try regex one more time on converted response
                    result_action = self.parse_action_with_re(str(converted_response))
            except Exception as e:
                logger.error(f"Converter parsing failed: {str(e)}")
                raise ResponseError("Failed to parse response using all available methods")
        
        # Validate the parsed result
        if not result_action:
            raise ResponseError("Response is an invalid JSON blob or Empty!")
        elif result_action.get("action") == '':
            raise ResponseError("Response action is Empty, Please try again.")
            
        result_thought = result_action.get("thought")
        return result_thought, result_action

    def parse_action_with_re(self, message, mode):
        # 根据mode选择不同的正则pattern
        if mode == "vision":
            pattern = r'"thought"\s*:\s*"([^"]*)"\s*,\s*"action"\s*:\s*"([^"]*)"\s*,\s*"action_input"\s*:\s*"([^"]*)"\s*,\s*"coordinates"\s*:\s*{\s*"x"\s*:\s*(-?\d+)\s*,\s*"y"\s*:\s*(-?\d+)\s*}\s*,\s*"description"\s*:\s*"([^"]*)"'
        else:
            pattern = r'"thought"\s*:\s*"([^"]*)"\s*,\s*"action"\s*:\s*"([^"]*)"\s*,\s*"action_input"\s*:\s*"([^"]*)"\s*,\s*"element_id"\s*:\s*(null|\d*)\s*,\s*"description"\s*:\s*"([^"]*)"'
        
        match = re.search(pattern, message)
        if match:
            if mode == "vision":
                thought = str(match.group(1))
                action = str(match.group(2))
                action_input = str(match.group(3))
                x_coordinate = int(match.group(4)) 
                y_coordinate = int(match.group(5))
                description = str(match.group(6))
                
                thought = re.sub(r'\s+', ' ', thought).strip()
                action = re.sub(r'\s+', ' ', action).strip()
                action_input = re.sub(r'\s+', ' ', action_input).strip()
                description = re.sub(r'\s+', ' ', description).strip()
                
                result_dict = {
                    "thought": thought,
                    "action": action,
                    "action_input": action_input,
                    "coordinates": {
                        "x": x_coordinate,
                        "y": y_coordinate
                    },
                    "description": description
                }
            else:
                thought = str(match.group(1))
                action = str(match.group(2))
                action_input = str(match.group(3))
                element_id = str(match.group(4))
                description = str(match.group(5))
                
                thought = re.sub(r'\s+', ' ', thought).strip()
                action = re.sub(r'\s+', ' ', action).strip()
                action_input = re.sub(r'\s+', ' ', action_input).strip()
                element_id = re.sub(r'\s+', ' ', element_id).strip()
                description = re.sub(r'\s+', ' ', description).strip()
                
                result_dict = {
                    "thought": thought,
                    "action": action,
                    "action_input": action_input,
                    "element_id": element_id,
                    "description": description
                }
                
            return result_dict
        return None

    def parse_action(self, message):
        message_substring = extract_longest_substring(message)
        decoded_result = {}
        decoded_result = json5.loads(message_substring)
        print("decode result: ", decoded_result)
        return decoded_result

    def extract_status_and_description(self, message) -> dict:
        try:
            description = re.findall("```(.*?)```", message, re.S)[0]
            status_description = self.parse_action(description)
        except:
            try:
                description = message
                status_description = self.parse_action(description)
            except:
                description = message.split("description:")[-1].strip()
                status_description = self.parse_action(description)

        return status_description

    def extract_score_and_description(self, message) -> dict:
        result_score = "null"
        try:
            result_score = re.findall(
                "score:(.*?)description:", message, re.S)[0].strip()
        except:
            try:
                result_score = message.split("description:")[0].strip()
            except:
                result_score = "null"
        try:
            description = re.findall("```(.*?)```", message, re.S)[0]
        except:
            description = message.split("description:")[-1].strip()
        score_description = self.parse_action(description)
        return score_description

    @staticmethod
    def get_element_id(input_str) -> str:
        # First, try to parse with json.loads()

        # If JSON parsing fails, try to extract with a regular expression
        pattern = r'["\']element_id["\']:\s*["\']?(\d+)["\']?,\s*["\']'
        match = re.search(pattern, input_str)
        if match:
            return match.group(1)
        else:
            return '-1'
