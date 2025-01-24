import os
import json
from .dataset_io import GraphQLClient

class AnnotationDataDownloader:
    def __init__(self, config):
        """
        初始化下载器
        config: 字典格式的配置
        """
        self.challenge_id = config.get('challenge_id')
        self.save_path = config.get('save_path')
        
        # 如果配置中提供了凭证，则设置环境变量
        if 'username' in config:
            os.environ['iMEAN_USERNAME'] = config['username']
        if 'password' in config:
            os.environ['iMEAN_PASSWORD'] = config['password']
            
        self.client = GraphQLClient()
        
    def download_annotations(self):
        """从iMean平台下载标注数据"""
        try:
            # 登录
            self.client.login()
            
            # 确保保存路径存在
            os.makedirs(self.save_path, exist_ok=True)
            
            # 下载数据
            self.client.export_atom_flows(
                challenge_id=self.challenge_id,
                save_path=self.save_path
            )
            
            # 读取下载的JSON文件
            json_files = [f for f in os.listdir(self.save_path) 
                         if f.endswith('.json')]
            
            if not json_files:
                raise Exception("No JSON files found in the downloaded data")
                
            data = []
            for json_file in json_files:
                file_path = os.path.join(self.save_path, json_file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data.extend(json.load(f))
                    
            return data
            
        except Exception as e:
            raise Exception(f"Failed to download annotations: {str(e)}")
    
    def save_raw_data(self, data, output_path):
        """保存原始数据到指定路径"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False) 