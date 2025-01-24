import json
import os
import copy
import logging
from typing import Dict, List, Any
from .utils import download_json, format_node, find_node_by_path, find_node_by_axtid

class SFTConverter:
    """将处理后的轨迹数据转换为SFT训练格式"""
    
    def __init__(self, config: Dict):
        self.config = config
        self._setup_logging()
        self._setup_templates()
        
    def _setup_logging(self):
        """设置日志"""
        log_dir = self.config.get('log_dir', 'logs/converter')
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(log_dir, 'converter.log')),
                logging.StreamHandler()
            ]
        )
        
    def _setup_templates(self):
        """设置提示模板"""
        # 系统提示信息
        self.prompt_system = '''
# CONTEXT

You are an autonomous intelligent agent tasked with navigating a web browser to accomplish various web-based tasks. Your success depends on effectively utilizing the specific actions available to you. Below is the information and guidance you will have during the task:

## TASK INFORMATION

1. **User's Objective**: The goal you are tasked to achieve.  
2. **Current Web Page's Accessibility Tree**: A simplified representation of the webpage, providing key information about its elements.  
3. **Current Web Page's URL**: The URL of the page you are currently viewing.  
4. **Previous Action List**: A record of all the actions you have performed so far, useful for tracking your progress.  

## AVAILABLE ACTIONS

### 1. **Page Operation Actions**
- click [id]: Click on a webpage element identified by its id.  
- type [id][content]: Type content into the field with the specified id.  
- hover [id]: Hover over an element identified by its id.  
- press_enter: Simulate pressing the "Enter" key.  

### 2. **Completion Action**
- stop [answer]: Use this action when you believe the task is complete.

## RULES

1. Only issue actions that are valid based on the current observation.  
2. Perform one action at a time.
3. Format actions correctly using the specified structure.
'''

        # 输入提示模板
        self.prompt_input_template = '''
# OBSERVATION

{axtree}

# URL

{url}

# OBJECTIVE

{objective}

# PREVIOUS ACTIONS

{action_list}
'''

        # 输出提示模板
        self.prompt_output_template = '''
Based on the observation and objective, I will:

{action}
'''

        # 动作模板
        self.action_template = '''
## Action {i}
- action_type: {action_type}
- action_value: {action_value}
'''

    def convert_to_sft_format(self, processed_data: List[Dict]) -> List[Dict]:
        """转换为SFT训练格式"""
        sft_data = []
        
        for traj_idx, trajectory in enumerate(processed_data):
            logging.info(f"Processing trajectory {traj_idx}: {trajectory.get('title', 'No title')}")
            
            try:
                objective = trajectory.get('title', '')
                steps_str = trajectory.get('steps', '[]')
                steps = json.loads(steps_str)
                logging.info(f"Found {len(steps)} steps in trajectory")
                
                # 创建轨迹特定的目录
                traj_dirs = self._create_trajectory_dirs(traj_idx)
                
                # 处理每个步骤
                for step_idx, step in enumerate(steps):
                    logging.info(f"Processing step {step_idx}")
                    
                    if not self._validate_step(step):
                        continue
                    
                    try:
                        # 处理 axtree 数据
                        formatted_axtree, retrieved_axtree = self._process_axtree(step, traj_idx, step_idx, traj_dirs)
                        if not formatted_axtree or not retrieved_axtree:
                            continue
                            
                        # 构建动作历史
                        action_list = self._build_action_list(steps[:step_idx])
                        
                        # 构建当前动作
                        current_action = {
                            "action_type": step["type"],
                            "action_id": step.get("axtId", ""),
                            "action_value": step.get("value", "")
                        }
                        
                        # 构建训练样本
                        sample = {
                            "prompt_system": self.prompt_system,
                            "prompt_input": self.prompt_input_template.format(
                                axtree=formatted_axtree,
                                url=step.get("href", ""),
                                objective=objective,
                                action_list=action_list
                            ),
                            "prompt_output": self.prompt_output_template.format(
                                action=json.dumps(current_action, ensure_ascii=False, indent=2)
                            ),
                            "metadata": {
                                "trajectory_id": traj_idx,
                                "step_id": step_idx,
                                "url": step.get("href", "")
                            }
                        }
                        
                        sft_data.append(sample)
                        logging.info(f"Successfully created sample for step {step_idx}")
                            
                    except Exception as e:
                        logging.error(f"Error processing step {step_idx}: {str(e)}")
                        continue
                        
            except Exception as e:
                logging.error(f"Error converting trajectory {traj_idx}: {str(e)}")
                continue
                
            if (traj_idx + 1) % 10 == 0:
                logging.info(f"Converted {traj_idx + 1} trajectories...")
                
        logging.info(f"Conversion completed. Generated {len(sft_data)} training samples")
        return sft_data
    
    def _validate_step(self, step: Dict) -> bool:
        """验证步骤数据的有效性"""
        required_fields = ['type', 'href']  # 移除了 formatted_axtree 的要求
        valid = all(field in step for field in required_fields)
        if not valid:
            missing_fields = [field for field in required_fields if field not in step]
            logging.warning(f"Missing required fields: {missing_fields}")
        return valid
    
    def _build_action_list(self, previous_steps: List[Dict]) -> str:
        """构建动作历史列表"""
        action_list = ""
        for i, step in enumerate(previous_steps):
            action_list += self.action_template.format(
                i=i,
                action_type=step["type"],
                action_value=step.get("value", "")
            )
        return action_list
    
    def save_sft_data(self, sft_data: List[Dict], output_path: str):
        """保存SFT训练数据"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 保存为JSONL格式
        with open(output_path, 'w', encoding='utf-8') as f:
            for sample in sft_data:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        logging.info(f"Saved {len(sft_data)} training samples to {output_path}")

    def _create_trajectory_dirs(self, traj_idx: int) -> Dict[str, str]:
        """创建轨迹相关的目录"""
        dirs = {
            'raw': os.path.join(self.config.get('raw_axtree_dir', 'data/raw_axtree'), str(traj_idx)),
            'formatted': os.path.join(self.config.get('formatted_axtree_dir', 'data/formatted_axtree'), str(traj_idx)),
            'retrieved': os.path.join(self.config.get('retrieved_axtree_dir', 'data/retrieved_axtree'), str(traj_idx))
        }
        
        for dir_path in dirs.values():
            os.makedirs(dir_path, exist_ok=True)
            
        return dirs

    def _process_axtree(self, step: Dict, traj_idx: int, step_idx: int, traj_dirs: Dict[str, str]) -> tuple:
        """处理单个步骤的 axtree 数据"""
        if not step.get("axTree"):
            logging.warning(f"Step {step_idx} has no axTree data")
            return None, None

        try:
            # 下载和保存原始 axtree
            raw_path = os.path.join(traj_dirs['raw'], f"{step_idx}.json")
            download_json(step["axTree"], raw_path)
            
            # 读取原始 axtree
            with open(raw_path, 'r', encoding='utf-8') as f:
                raw_axtree = json.load(f)
                
            # 格式化完整 axtree
            formatted_nodes = format_node(raw_axtree)
            formatted_axtree = "\n".join(formatted_nodes)
            
            # 保存格式化后的 axtree
            formatted_path = os.path.join(traj_dirs['formatted'], f"{step_idx}.txt")
            with open(formatted_path, 'w', encoding='utf-8') as f:
                f.write(formatted_axtree)
                
            # 查找目标节点
            retrieved_node = None
            if "axtId" in step and step["axtId"]:
                # 优先使用 axtId 查找
                logging.info(f"Searching node by axtId: {step['axtId']}")
                retrieved_node = find_node_by_axtid(raw_axtree, step["axtId"])
                if retrieved_node:
                    logging.info(f"Found node by axtId: {step['axtId']}")
                else:
                    logging.warning(f"Node not found by axtId: {step['axtId']}, falling back to path search")
            
            # 如果没有 axtId 或未找到，则使用 path 查找
            if retrieved_node is None and "path" in step:
                logging.info(f"Searching node by path: {step['path']}")
                path = ["html"] + step["path"].split('>')
                retrieved_node = find_node_by_path(raw_axtree, path)
                if retrieved_node:
                    logging.info(f"Found node by path")
                else:
                    logging.warning(f"Node not found by path: {step['path']}")
            
            if retrieved_node is None:
                logging.warning(f"No node found for step {step_idx}")
                return formatted_axtree, ""
                
            # 格式化检索到的节点
            retrieved_nodes = format_node(retrieved_node)
            retrieved_axtree = "\n".join(retrieved_nodes)
            
            # 保存检索到的节点
            retrieved_path = os.path.join(traj_dirs['retrieved'], f"{step_idx}.txt")
            with open(retrieved_path, 'w', encoding='utf-8') as f:
                f.write(retrieved_axtree)
                
            # 验证找到的节点的 axtId 是否匹配（如果原始步骤中有 axtId）
            if "axtId" in step and step["axtId"]:
                found_axt_id = retrieved_node.get("attributes", {}).get("data-imean-axt-id")
                if found_axt_id != step["axtId"]:
                    logging.warning(f"AxtId mismatch - Expected: {step['axtId']}, Found: {found_axt_id}")
            
            return formatted_axtree, retrieved_axtree
            
        except Exception as e:
            logging.error(f"Error processing axtree for step {step_idx}: {str(e)}")
            return None, None 