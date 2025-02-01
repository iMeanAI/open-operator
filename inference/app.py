import streamlit as st
import yaml
import logging
import asyncio
from pathlib import Path
from run import execute_task
from run import TaskRequest

def load_config():
    """Load configuration file"""
    with open("./inference/configs/agent_config.yaml", "r") as f:
        return yaml.safe_load(f)

def setup_logging(config):
    """Initialize logging configuration"""
    log_dir = Path(config['log_dir'])
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'inference.log'),
            logging.StreamHandler()
        ]
    )

async def run_inference(instruction: str, config: dict):
    """Run inference pipeline"""
    try:
        # Create TaskRequest with the instruction as task_name
        task_request = TaskRequest(
            task_name=instruction,
            observation_mode=config['mode'],
            planning_text_model=config['model']['selected'],
            global_reward_text_model=config['model']['selected'],
            toml_path="./inference/configs/setting.toml"
        )
        
        result = await execute_task(task_request)
        return result
    except Exception as e:
        logging.error(f"Error during inference: {str(e)}")
        raise

def main():
    st.title("Web Agent Inference")
    
    # Load config
    config = load_config()
    setup_logging(config)
    
    # Mode selection
    mode = st.selectbox(
        "Select Mode",
        ["dom"],
        help="Choose the inference mode"
    )
    
    # Model selection 
    model = st.selectbox(
        "Select Model",
        config['model']['available_models'],
        help="Choose the model to use"
    )
    
    # Input instruction
    instruction = st.text_input("Enter your instruction:")
    
    if st.button("Execute"):
        config['mode'] = mode
        config['model']['selected'] = model
        
        with st.spinner("Executing instruction..."):
            asyncio.run(run_inference(instruction, config))
            st.success("Execution completed!")

if __name__ == "__main__":
    main() 