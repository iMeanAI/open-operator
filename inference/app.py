import gradio as gr
import tomli
import logging
import asyncio
from pathlib import Path
from run import execute_task
from run import TaskRequest

def load_config():
    """Load configuration file"""
    with open("./inference/configs/setting.toml", "rb") as f:
        return tomli.load(f)

def setup_logging(config):
    """Initialize logging configuration"""
    log_dir = Path(config['basic']['log_dir'])
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, config['basic']['log_level']),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'inference.log'),
            logging.StreamHandler()
        ]
    )

async def run_inference(instruction: str, mode: str, model: str):
    """Run inference pipeline"""
    try:
        config = load_config()
        setup_logging(config)
        
        task_request = TaskRequest(
            task_name=instruction,
            observation_mode=mode,
            planning_text_model=model,
            global_reward_text_model=model,
            toml_path="./inference/configs/setting.toml"
        )
        
        result = await execute_task(task_request)
        return f"Execution completed successfully!\nResult: {result}"
    except Exception as e:
        error_msg = f"Error during inference: {str(e)}"
        logging.error(error_msg)
        return error_msg

def inference_interface(instruction: str, mode: str, model: str):
    return asyncio.run(run_inference(instruction, mode, model))

def use_example_1():
    return "Find all latest blog posts on iMean.ai"

def use_example_2():
    return "Find me paper submission dates of ACL2025"

def create_demo():
    config = load_config()
    
    with gr.Blocks(title="Open-Operator") as demo:
        gr.Markdown("""
        # Open-Operator
        Enter an instruction and select mode and model to execute the web agent.
        """)
        
        with gr.Row():
            with gr.Column(scale=1):
                instruction_input = gr.Textbox(
                    label="Enter your instruction",
                    placeholder="Type your instruction here or use example tasks below..."
                )
                with gr.Column(scale=1):
                    example1_btn = gr.Button(
                        "Find all latest blog posts on iMean.ai",
                        size="sm",
                        min_width=100
                    )
                    example2_btn = gr.Button(
                        "Find paper submission dates of ACL2025",
                        size="sm",
                        min_width=100
                    )
                mode_input = gr.Dropdown(
                    choices=["dom"],
                    value="dom",
                    label="Select Mode"
                )
                model_input = gr.Dropdown(
                    choices=config['model']['available_models'],
                    label="Select Model",
                    value=config['model']['selected']
                )         
                
                submit_btn = gr.Button("Execute", variant="primary")
        
        output = gr.Textbox(label="Result")
        
        # Button click handlers
        example1_btn.click(fn=use_example_1, outputs=[instruction_input])
        example2_btn.click(fn=use_example_2, outputs=[instruction_input])
        submit_btn.click(
            fn=inference_interface,
            inputs=[instruction_input, mode_input, model_input],
            outputs=output
        )
        
    return demo

if __name__ == "__main__":
    demo = create_demo()
    # Launch with share=True to get a public URL
    demo.launch(share=True, server_name="0.0.0.0") 