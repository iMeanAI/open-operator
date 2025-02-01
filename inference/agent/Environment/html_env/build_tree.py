from collections import deque
from lxml.html import etree
from io import StringIO
import json
import re
import traceback

from .utils import ElementNode, TagNameList, MapTagNameList, DelTagNameList, stringfy_selector
from .active_elements import ActiveElements
import logging

logger = logging.getLogger(__name__)


import copy


class HTMLTree:
    def __init__(self):
        self.elementNodes = [ElementNode] * 100000
        self.rawNode2id: dict = {}
        self.element2id: dict = {}
        self.id2rawNode: dict = {}
        self.valid: list[bool] = [False] * 100000
        self.nodeCounts: int
        self.nodeDict = {}
        self.element_value = {}
        self.link_index = {}
        self.pruningTreeNode = None

    def fetch_html_content(self, html_content) -> str:
        try:
            self.__init__()
            if not html_content or not html_content.strip():
                logger.error("Empty HTML content received")
                return ""
            
            # 添加基本的HTML结构检查
            if not ("<html" in html_content and "<body" in html_content):
                logger.error("Invalid HTML structure")
                return ""
            
            parser = etree.HTMLParser(recover=True, remove_blank_text=True)
            try:
                self.tree = etree.parse(StringIO(html_content), parser)
            except Exception as e:
                logger.error(f"Failed to parse HTML content: {e}")
                return ""
            
            if self.tree is None:
                logger.error("Failed to create HTML tree")
                return ""
            
            self.copy_tree = copy.deepcopy(self.tree)
            root = self.tree.getroot()
            
            if root is None:
                logger.error("No root element found in HTML tree")
                return ""
            
            # 检查是否存在基本的HTML结构
            body = root.find(".//body")
            if body is None:
                logger.error("No body element found")
                return ""
            
            logger.info(f"Found {len(root.getchildren())} child elements in root")
            logger.info(f"Found {len(body.getchildren())} child elements in body")
            
            self.init_html_tree(root)
            self.build_html_tree(root)
            
            if self.pruningTreeNode is None:
                logger.error("Failed to initialize pruningTreeNode")
                return ""
            
            return self.prune_tree()
        except Exception as e:
            logger.error(f"Error in fetch_html_content: {e}")
            return ""

    @staticmethod
    def build_node(node, idx: int) -> ElementNode:
        elementNode = ElementNode()
        elementNode["nodeId"] = idx
        elementNode["tagName"] = node.tag
        elementNode["text"] = node.text
        elementNode["attributes"] = node.attrib
        elementNode["childIds"] = []
        elementNode["parentId"] = ""
        elementNode["siblingId"] = ""
        elementNode["twinId"] = ""
        elementNode["depth"] = 1
        elementNode["htmlContents"] = etree.tostring(
            node, pretty_print=True).decode()
        return elementNode

    def build_mapping(self) -> None:
        self.element2id = {value["nodeId"]: index for index,
                           value in enumerate(self.elementNodes)}
        self.id2rawNode = {str(index): value for value,
                           index in self.rawNode2id.items()}

    def init_html_tree(self, root) -> None:
        if root is None:
            logger.error("Root node is None")
            return
        
        node_queue = deque([root])
        node_id = 0
        
        while node_queue:
            node = node_queue.popleft()
            if node is None:
                continue
            
            try:
                self.elementNodes[node_id] = HTMLTree().build_node(node, node_id)
                self.rawNode2id[node] = node_id
                node_id += 1
                
                children = node.getchildren()
                logger.debug(f"Node {node_id} has {len(children)} children")
                
                for child in children:
                    if child is not None and child.tag not in DelTagNameList:
                        node_queue.append(child)
                    
            except Exception as e:
                logger.error(f"Error processing node {node_id}: {e}")
                continue
            
        self.build_mapping()
        self.nodeCounts = node_id
        self.valid = self.valid[:self.nodeCounts + 1]

    def build_html_tree(self, root) -> None:
        try:
            node_queue = deque([root])
            root_id = self.rawNode2id[root]
            self.elementNodes[root_id]["parentId"] = -1
            while node_queue:
                node = node_queue.popleft()
                if node is None or node.tag in DelTagNameList:
                    continue
                    
                parent_id = self.rawNode2id.get(node)
                if parent_id is None:
                    continue
                    
                tag_st = {}
                sibling_id = 1
                
                for child in node.getchildren():
                    if child is None or child.tag in DelTagNameList:
                        continue
                        
                    child_id = self.rawNode2id.get(child)
                    if child_id is None:
                        continue
                        
                    tag_name = self.elementNodes[child_id].get("tagName")
                    if not tag_name:
                        continue
                        
                    tag_st[tag_name] = tag_st.get(tag_name, 0) + 1
                    twin_id = tag_st.get(tag_name)
                    
                    self.elementNodes[parent_id]["childIds"].append(child_id)
                    self.elementNodes[child_id]["parentId"] = parent_id
                    self.elementNodes[child_id]["twinId"] = twin_id
                    self.elementNodes[child_id]["depth"] = self.elementNodes[parent_id]["depth"] + 1
                    self.elementNodes[child_id]["siblingId"] = sibling_id
                    node_queue.append(child)
                    sibling_id += 1
                    
            self.pruningTreeNode = copy.deepcopy(self.elementNodes)
            
            # 确保pruningTreeNode[0]存在且有效
            if not self.pruningTreeNode or not self.pruningTreeNode[0]:
                logger.error("Failed to initialize pruningTreeNode properly")
                self.pruningTreeNode = [ElementNode()]
                self.pruningTreeNode[0]["nodeId"] = 0
                self.pruningTreeNode[0]["childIds"] = []
                self.pruningTreeNode[0]["parentId"] = -1
                
        except Exception as e:
            logger.error(f"Error in build_html_tree: {e}")
            self.pruningTreeNode = [ElementNode()]
            self.pruningTreeNode[0]["nodeId"] = 0
            self.pruningTreeNode[0]["childIds"] = []
            self.pruningTreeNode[0]["parentId"] = -1

    def get_xpath(self, idx: int) -> str:
        locator_str = ""
        current_node = self.elementNodes[idx]
        tag_name = current_node["tagName"]
        twinId = current_node["twinId"]
        locator_str = "/" + tag_name + "[" + str(twinId) + "]"
        while current_node["parentId"] != 0:
            parentid = current_node["parentId"]
            current_node = self.elementNodes[parentid]
            current_tag_name = current_node["tagName"]
            twinId = current_node["twinId"]
            locator_str = "/" + current_tag_name + \
                "[" + str(twinId) + "]" + locator_str
        parentid = current_node["parentId"]
        current_node = self.elementNodes[parentid]
        current_tag_name = current_node["tagName"]
        return "/" + current_tag_name + locator_str

    def get_selector(self, idx: int) -> str:
        selector_str = ""
        current_node = self.elementNodes[idx]
        while current_node["parentId"] != -1:
            tag_name = current_node["tagName"]
            siblingId = str(current_node["siblingId"])
            if current_node["attributes"].get('id'):
                current_selector = stringfy_selector(
                    current_node["attributes"].get('id'))
                return "#" + current_selector + selector_str
            if len(self.elementNodes[current_node["parentId"]]["childIds"]) > 1:
                uu_twin_node = True
                uu_id = True
                for childId in self.elementNodes[current_node["parentId"]]["childIds"]:
                    sib_node = self.elementNodes[childId]
                    if sib_node["nodeId"] != current_node["nodeId"] and current_node["attributes"].get('class') and sib_node["attributes"].get("class") == current_node["attributes"].get('class'):
                        uu_twin_node = False
                    if sib_node["nodeId"] != current_node["nodeId"] and current_node["tagName"] == sib_node["tagName"]:
                        uu_id = False
                if uu_id:
                    selector_str = " > " + tag_name + selector_str
                elif current_node["attributes"].get('class') and uu_twin_node is True:
                    # fix div.IbBox.Whs\(n\)
                    selector_str = " > " + tag_name + "." + \
                        stringfy_selector(
                            current_node["attributes"].get('class')) + selector_str
                else:
                    selector_str = " > " + tag_name + \
                        ":nth-child(" + siblingId + ")" + selector_str
            else:
                selector_str = " > " + tag_name + selector_str
            current_node = self.elementNodes[current_node["parentId"]]
        return current_node["tagName"] + selector_str

    def is_valid(self, idx: int) -> bool:
        node = self.pruningTreeNode[idx]
        if node["tagName"] in TagNameList:
            return ActiveElements.is_valid_element(node)
    
    def prune_tree(self) -> str:
        """Traverse each element to determine if it is valid and prune"""
        result_list = []
        root = self.pruningTreeNode[0]
        if root is None:
            result_list = []
        stack = [root]
        while stack:
            node = stack.pop()
            nodeId = node["nodeId"]
            result_list.append(nodeId)
            children = []
            for childId in node["childIds"]:
                childNode = self.pruningTreeNode[childId]
                children.append(childNode)
            stack.extend(children)
        result = result_list[::-1]
        for nodeId in result:
            if self.is_valid(nodeId) or self.valid[nodeId] is True:
                rawNode = self.id2rawNode.get(str(nodeId))
                if rawNode is not None:
                    html_contents = etree.tostring(rawNode, pretty_print=True).decode()
                    self.pruningTreeNode[nodeId]["htmlContents"] = html_contents
                    self.valid[nodeId] = True
                    current_id = nodeId
                    while self.pruningTreeNode[current_id]["parentId"] != -1:
                        parent_id = self.pruningTreeNode[current_id]["parentId"]
                        self.valid[parent_id] = True
                        current_id = parent_id
            else:
                rawNode = self.id2rawNode.get(str(nodeId))
                if rawNode is not None and rawNode.getparent() is not None:
                    try:
                        rawNode.getparent().remove(rawNode)
                    except Exception as e:
                        logger.error(f"Failed to remove node: {e}")
                current_node = self.pruningTreeNode[nodeId]
                current_node["htmlContents"] = ""
                parentid = current_node["parentId"]
                if nodeId in self.pruningTreeNode[parentid]["childIds"]:
                    self.pruningTreeNode[parentid]["childIds"].remove(nodeId)
                self.valid[nodeId] = False
        return self.pruningTreeNode[0]["htmlContents"]

    def get_element_contents(self, idx: int) -> str:
        node = self.elementNodes[idx]
        html_content = node["htmlContents"]
        return html_content

    def get_tag_name(self, element: ElementNode) -> (str, int):  # type: ignore
        # 首先检查是否为文本节点
        if element["text"] and element["text"].strip():
            return ("text", element["nodeId"])
        
        tag_name = ActiveElements.get_element_tagName(element)
        tag_idx = element["nodeId"]
        if tag_name == "unknown":
            tag_name = element["tagName"]
            tag_idx = element["nodeId"]
            if tag_name in MapTagNameList:
                parent_element = self.pruningTreeNode[element["parentId"]]
                return self.get_tag_name(parent_element)
            else:
                return ("statictext", tag_idx)
        return (tag_name, tag_idx)
    
    def get_element_link(self, node: dict) -> str:
        """获取元素的链接（如果存在）"""
        if "attributes" in node and "href" in node["attributes"]:
            return node["attributes"]["href"]
        return ""
    
    def build_dom_tree(self) -> str:
        root = self.pruningTreeNode[0]
        stack = [root]
        contents = ""
        num = 0
        self.link_index = {}
        pending_links = {}
        
        while stack:
            node = stack.pop()
            if self.valid[node["nodeId"]] is True:
                content_text = HTMLTree().process_element_contents(node)
                tag_name, tag_idx = self.get_tag_name(node)
                
                # 获取href属性
                href = node.get("attributes", {}).get("href", "")
                
                if href and not href.startswith('#'):
                    # 如果当前节点没有文本内容，查找最近的文本
                    if not content_text.strip():
                        content_text, distance = self.find_nearest_text(node["nodeId"])
                        
                    if content_text.strip():
                        # 找到了相关文本，直接创建链接
                        num += 1
                        self.nodeDict[num] = tag_idx
                        self.link_index[num] = {
                            'href': href,
                            'text': content_text,
                            'tag_name': tag_name,
                            'node_id': node["nodeId"]
                        }
                        indent = "  " * (node["depth"]-1)
                        contents += f"{indent}[{num}] link '{content_text}' [get link id🔗]\n"
                    else:
                        # 没找到文本，存储待处理的链接
                        pending_links[node["nodeId"]] = {
                            'href': href,
                            'tag_name': tag_name,
                            'depth': node["depth"]
                        }
                elif content_text.strip():
                    # 检查是否有待处理的链接可以与当前文本匹配
                    matched_link = None
                    min_distance = float('inf')
                    
                    for link_node_id, link_info in list(pending_links.items()):  # 使用list()避免字典修改错误
                        # 计算节点距离（基于DOM树深度差异）
                        distance = abs(node["depth"] - link_info['depth'])
                        if distance < min_distance and distance <= 2:  # 添加直接的距离限制
                            min_distance = distance
                            matched_link = (link_node_id, link_info)
                    
                    if matched_link:
                        link_node_id, link_info = matched_link
                        num += 1
                        self.nodeDict[num] = tag_idx
                        self.link_index[num] = {
                            'href': link_info['href'],
                            'text': content_text,
                            'tag_name': link_info['tag_name'],
                            'node_id': link_node_id
                        }
                        indent = "  " * (node["depth"]-1)
                        contents += f"{indent}[{num}] link '{content_text}' [get link id🔗]\n"
                        del pending_links[link_node_id]
                    elif tag_name.lower() != "statictext":
                        # 普通文本节点
                        num += 1
                        self.nodeDict[num] = tag_idx
                        indent = "  " * (node["depth"]-1)
                        contents += f"{indent}[{num}] {tag_name} '{content_text}'\n"
                    
                    self.element_value[str(tag_idx)] = content_text
                
                children = []
                for child_id in node["childIds"]:
                    children.append(self.pruningTreeNode[child_id])
                stack.extend(reversed(children))
        
        logger.debug(f"Built link index with {len(self.link_index)} entries")
        logger.debug(f"Remaining unmatched links: {len(pending_links)}")
        return contents

    def get_selector_and_xpath(self, idx: int) -> (str, str):  # type: ignore
        try:
            logger.debug(f"Getting selector and xpath for element id: {idx}")
            logger.debug(f"Current nodeDict keys: {list(self.nodeDict.keys())}")
            
            if idx not in self.nodeDict:
                logger.error(f"Element id {idx} not found in nodeDict")
                return None, None
            
            selector = self.get_selector(idx)
            logger.debug(f"Generated selector: {selector}")
            
            xpath = self.get_xpath(idx)
            logger.debug(f"Generated xpath: {xpath}")
            
            return selector, xpath
        except Exception as e:
            logger.error(f"Error in get_selector_and_xpath for id {idx}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return None, None

    @staticmethod
    def process_element_contents(element: ElementNode) -> str:
        # 处理文本内容
        if element["text"]:
            text = element["text"].strip()
            # 过滤掉无效的文本内容
            if text and not text.isspace() and len(text) > 1:
                # 过滤掉系统消息和无意义内容
                invalid_patterns = [ 
                    "**Key Information**",
                    "chars omitted",
                    "line too long",
                ]
                if not any(pattern in text for pattern in invalid_patterns):
                    return text

        # 处理可交互元素
        html_text = ActiveElements.get_element_value(element)
        if html_text:
            text = html_text.replace("\n", "").replace("\t", "").strip()
            if text and not text.isspace() and len(text) > 1:
                return text
                
        return ""

    def get_element_value(self, element_id: int) -> str:
        try:
            logger.debug(f"Getting element value for id: {element_id}")
            
            if str(element_id) not in self.element_value:
                logger.error(f"Element id {element_id} not found in element_value dictionary")
                logger.debug(f"Available element_value keys: {list(self.element_value.keys())}")
                return ""
            
            value = self.element_value[str(element_id)]
            logger.debug(f"Found element value: {value}")
            return value
        except Exception as e:
            logger.error(f"Error in get_element_value for id {element_id}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return ""

    def find_nearest_text(self, node_id: int, visited_nodes: set = None, max_depth: int = 2) -> tuple[str, int]:
        """查找最近的有意义的文本内容"""
        if visited_nodes is None:
            visited_nodes = set()
        
        # 防止重复访问同一节点
        if node_id in visited_nodes or max_depth < 0:
            return "", float('inf')
        
        visited_nodes.add(node_id)
        node = self.pruningTreeNode[node_id]
        
        # 首先检查当前节点
        content = HTMLTree().process_element_contents(node)
        if content.strip():
            return content, 0
        
        min_depth = float('inf')
        best_content = ""
        
        # 检查子节点
        for child_id in node["childIds"]:
            if child_id not in visited_nodes:
                content, depth = self.find_nearest_text(child_id, visited_nodes, max_depth - 1)
                if content.strip() and depth < min_depth:
                    min_depth = depth
                    best_content = content
        
        # 检查父节点
        parent_id = node["parentId"]
        if parent_id != -1 and parent_id not in visited_nodes:
            content, depth = self.find_nearest_text(parent_id, visited_nodes, max_depth - 1)
            if content.strip() and depth < min_depth:
                min_depth = depth
                best_content = content
        
        # 检查兄弟节点
        if parent_id != -1:
            parent = self.pruningTreeNode[parent_id]
            for sibling_id in parent["childIds"]:
                if sibling_id != node_id and sibling_id not in visited_nodes:
                    content, depth = self.find_nearest_text(sibling_id, visited_nodes, max_depth - 1)
                    if content.strip() and depth < min_depth:
                        min_depth = depth
                        best_content = content
        
        return (best_content, min_depth + 1) if best_content else ("", float('inf'))


def process_final_answer(final_answer: str | list | dict, html_tree: HTMLTree) -> str:
    """Process final answer to resolve any link IDs"""
    try:
        # Handle JSON string that starts with ```json
        if isinstance(final_answer, str):
            # Remove markdown code block syntax if present
            if final_answer.startswith('```'):
                final_answer = '\n'.join(final_answer.split('\n')[1:-1])
            
        # Convert final_answer to dict if it's already a Python object
        if isinstance(final_answer, (list, dict)):
            answer_dict = final_answer
        else:
            # Parse the final answer if it's a string
            answer_dict = json.loads(final_answer)
        
        def extract_number(value: str | int) -> int | None:
            """Extract the first number from a string or return the number itself"""
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                numbers = re.findall(r'\d+', value)
                return int(numbers[0]) if numbers else None
            return None
        
        # Recursively process dictionary to find and resolve link IDs
        def resolve_links(obj):
            if isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    if 'link' in key.lower():
                        # Handle single link ID
                        if isinstance(value, (int, str)):
                            link_id = extract_number(value)
                            result[key] = html_tree.link_index.get(link_id, value) if link_id else value
                        # Handle array of link IDs
                        elif isinstance(value, list):
                            result[key] = [
                                html_tree.link_index.get(
                                    extract_number(id),
                                    id
                                ) for id in value
                            ]
                        else:
                            result[key] = value
                    else:
                        # Recursively process nested values
                        result[key] = resolve_links(value)
                return result
            elif isinstance(obj, list):
                # Process each item in the list
                return [resolve_links(item) for item in obj]
            return obj
        
        processed_answer = resolve_links(answer_dict)
        return json.dumps(processed_answer, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error processing final answer: {e}")
        # If there's any error in processing, return the original as a JSON string
        if isinstance(final_answer, str):
            # Remove markdown code block syntax if present
            if final_answer.startswith('```'):
                final_answer = '\n'.join(final_answer.split('\n')[1:-1])
        return json.dumps(final_answer) if isinstance(final_answer, (list, dict)) else str(final_answer)


__all__ = [
    "HTMLTree"
]