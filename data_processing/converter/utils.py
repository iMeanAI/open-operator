import requests
import json

def download_json(url, output_file='output.json'):
    try:
        # Send GET request
        response = requests.get(url)
        response.raise_for_status()
        
        # Save JSON data to file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(response.json(), f, ensure_ascii=False, indent=2)
            
    except requests.exceptions.RequestException as e:
        print(f"Error downloading the file: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")


def find_node_by_axtid(node, axt_id):
    """
    Recursively traverse axtree to find node with specified axt_id.
    
    Args:
        node: Current node
        axt_id: Target axt_id to find
    Returns:
        Matching node object if found, None otherwise
    """
    if node is None:
        return None
    
    # Check current node's axt_id
    current_axt_id = node.get("attributes", {}).get("data-imean-axt-id")
    if current_axt_id == axt_id:
        return node
        
    # Check child nodes recursively
    for child in node.get("children", []):
        result = find_node_by_axtid(child, axt_id)
        if result:
            return result
            
    return None

def find_node_by_path(node, path, current_level=0):
    """
    Recursively traverse axtree to find node at specified path.
    Used as fallback when axtId is not available or not found.
    """
    if node is None:
        return None
    
    html_tag = node.get("attributes", {}).get("html_tag", "")

    if html_tag != path[current_level]:
        return None

    if current_level == len(path) - 1:
        return node

    for child in node.get("children", []):
        result = find_node_by_path(child, path, current_level + 1)
        if result:
            return result

    return None

def format_node(node, level=0):
    """Format node and its children into a readable tree structure"""
    result = []
    indent = "  " * level
    
    if node is None:
        return result
    
    # Get node attributes
    axt_id = node.get("attributes", {}).get("data-imean-axt-id")
    role = node.get("role")
    name = node.get("name")
    value = node.get("value")
    
    if axt_id and role:
        formatted = indent + f"[{axt_id}] {role}"
        if name:
            formatted += f" '{name}'"
        elif value:
            formatted += f" '{value}'"
        result.append(formatted)
    
    # Process children recursively
    children = node.get("children", [])
    for child in children:
        result.extend(format_node(child, level + 1))
        
    return result
    