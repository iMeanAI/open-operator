from abc import ABC, abstractmethod
import json
import os
import logging
from typing import Dict, List, Any

class BaseProcessor(ABC):
    """数据处理基类"""
    def __init__(self, config: Dict):
        self.config = config
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        log_dir = self.config.get('log_dir', 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(log_dir, 'preprocessing.log')),
                logging.StreamHandler()
            ]
        )
    
    @abstractmethod
    def process(self, raw_data: List[Dict]) -> List[Dict]:
        """处理原始数据的抽象方法"""
        pass
    
    def save_processed_data(self, processed_data: List[Dict], output_path: str):
        """保存处理后的数据"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=2)

class DOMTreeProcessor(BaseProcessor):
    def process(self, raw_data):
        """处理DOM树模式的数据"""
        processed_data = []
        for item in raw_data:
            processed_item = {
                'instruction': self._process_instruction(item),
                'input': self._process_dom_observation(item),
                'output': self._process_action_sequence(item)
            }
            processed_data.append(processed_item)
        return processed_data

class VisionProcessor(BaseProcessor):
    def process(self, raw_data):
        """处理视觉模式的数据"""
        processed_data = {
            'planning_data': [],
            'grounding_data': []
        }
        for item in raw_data:
            # 处理planning数据
            planning_item = {
                'instruction': item['instruction'],
                'observation': self._process_image(item['screenshot']),
                'action': item['action']
            }
            
            # 处理grounding数据
            grounding_item = {
                'screenshot': self._process_image(item['screenshot']),
                'action': item['action'],
                'coordinates': item['click_position']
            }
            
            processed_data['planning_data'].append(planning_item)
            processed_data['grounding_data'].append(grounding_item)
            
        return processed_data 