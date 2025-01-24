from abc import ABC, abstractmethod
import json
import os
import logging
from typing import Dict, List, Any

class BaseProcessor(ABC):
    """Base class for data processing"""
    def __init__(self, config: Dict):
        self.config = config
        self._setup_logging()
    
    def _setup_logging(self):
        """Initialize logging configuration"""
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
        """Abstract method for processing raw data"""
        pass
    
    def save_processed_data(self, processed_data: List[Dict], output_path: str):
        """Save processed data to file"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=2)

class DOMTreeProcessor(BaseProcessor):
    def process(self, raw_data):
        """Process data in DOM tree mode"""
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
        """Process data in vision mode"""
        processed_data = {
            'planning_data': [],
            'grounding_data': []
        }
        for item in raw_data:
            # Process planning data
            planning_item = {
                'instruction': item['instruction'],
                'observation': self._process_image(item['screenshot']),
                'action': item['action']
            }
            
            # Process grounding data
            grounding_item = {
                'screenshot': self._process_image(item['screenshot']),
                'action': item['action'],
                'coordinates': item['click_position']
            }
            
            processed_data['planning_data'].append(planning_item)
            processed_data['grounding_data'].append(grounding_item)
            
        return processed_data 