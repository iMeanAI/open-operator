from .base_processor import BaseProcessor
from typing import Dict, List, Any
import json
import copy
import logging
import os

class DOMProcessor(BaseProcessor):
    """DOM树数据处理器"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.processed_count = 0
        self.error_count = 0
    
    def process(self, raw_data: List[Dict]) -> List[Dict]:
        """处理DOM树轨迹数据"""
        processed_data = []
        
        for traj_idx, trajectory in enumerate(raw_data):
            try:
                # 确保steps是字符串形式
                if isinstance(trajectory.get('steps'), list):
                    trajectory['steps'] = json.dumps(trajectory['steps'])
                
                processed_traj = self._process_single_trajectory(trajectory)
                if processed_traj:
                    processed_data.append(processed_traj)
                    self.processed_count += 1
                    
            except Exception as e:
                self.error_count += 1
                logging.error(f"Error processing trajectory {traj_idx}: {str(e)}")
                continue
        
        logging.info(f"Processing completed. "
                    f"Processed: {self.processed_count}, "
                    f"Errors: {self.error_count}")
        
        return processed_data
    
    def _process_single_trajectory(self, trajectory: Dict) -> Dict:
        """处理单条轨迹数据"""
        processed_traj = copy.deepcopy(trajectory)
        
        # 解析steps数据
        steps = json.loads(processed_traj['steps'])
        processed_steps = []
        
        for step in steps:
            processed_step = self._process_step(step)
            if processed_step:
                processed_steps.append(processed_step)
        
        # 重新转换为JSON字符串
        processed_traj['steps'] = json.dumps(processed_steps)
        return processed_traj
    
    def _process_step(self, step: Dict) -> Dict:
        """处理单个步骤数据"""
        processed_step = copy.deepcopy(step)
        
        # 处理必要的字段
        if not all(key in step for key in ['type', 'value', 'path']):
            logging.warning(f"Missing required fields in step: {step}")
            return None
        
        # 处理DOM路径
        processed_step['path'] = self._process_dom_path(step['path'])
        
        # 验证action类型和值
        if not self._validate_action(processed_step):
            return None
            
        return processed_step
    
    def _process_dom_path(self, path: str) -> str:
        """处理DOM路径"""
        # 移除开头的html标签(如果存在)
        if path.startswith('html>'):
            path = path[5:]
        return path
    
    def _validate_action(self, step: Dict) -> bool:
        """验证action的有效性"""
        valid_actions = {'click', 'type', 'hover', 'press_enter'}
        
        if step['type'] not in valid_actions:
            logging.warning(f"Invalid action type: {step['type']}")
            return False
            
        if step['type'] == 'type' and not step.get('value'):
            logging.warning("Missing value for type action")
            return False
            
        return True 

    def save_processed_data(self, data: list, file_path: str):
        """保存处理后的数据"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2) 