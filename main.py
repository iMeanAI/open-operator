import os
import json
import yaml
import logging
from data_processing.preprocessor.dom_processor import DOMProcessor
from data_processing.downloader.api_client import AnnotationDataDownloader
from data_processing.converter.data_converter import SFTConverter

def load_config(config_path: str) -> dict:
    """Load configuration file"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def setup_logging():
    """Initialize logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def load_processed_data(data_path: str) -> list:
    """Load processed data from file"""
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # 1. Load configuration
    try:
        config = load_config("configs/config.yaml")
    except Exception as e:
        print(f"Error loading config: {str(e)}")
        return
    
    # 2. Setup logging
    setup_logging()
    logging.info("Starting data processing pipeline...")
    
    # 3. Download data
    try:
        downloader = AnnotationDataDownloader(config['data_download'])
        raw_data = downloader.download_annotations()
        
        if config['data_download'].get('save_raw_data'):
            raw_data_path = os.path.join(
                config['data_download']['save_path'], 
                'raw_data.json'
            )
            downloader.save_raw_data(raw_data, raw_data_path)
            logging.info(f"Raw data saved to {raw_data_path}")
            
    except Exception as e:
        logging.error(f"Error downloading data: {str(e)}")
        return
    
    # 4. Preprocess data
    try:
        processor = DOMProcessor(config['data_processing'])
        processed_data = processor.process(raw_data)
        
        processed_data_path = os.path.join(
            config['data_processing']['save_path'],
            'processed_data.json'
        )
        processor.save_processed_data(processed_data, processed_data_path)
        logging.info(f"Processed data saved to {processed_data_path}")
        
    except Exception as e:
        logging.error(f"Error processing data: {str(e)}")
        return

    # 5. Convert to SFT format
    try:
        converter = SFTConverter(config['converter'])
    
        processed_data = load_processed_data(processed_data_path)
        logging.info(f"Loaded {len(processed_data)} processed trajectories")
        
        sft_data = converter.convert_to_sft_format(processed_data)
        
        sft_data_path = os.path.join(
            config['converter']['save_path'],
            'sft_data.json'
        )
        converter.save_sft_data(sft_data, sft_data_path)
        logging.info(f"SFT data saved to {sft_data_path}")
        
        logging.info(f"Conversion completed. Generated {len(sft_data)} SFT examples")
        logging.info("Data processing pipeline completed successfully")
    except Exception as e:
        logging.error(f"Error converting data to SFT format: {str(e)}")
        return

if __name__ == "__main__":
    main() 