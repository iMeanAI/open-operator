from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Union, List
import uvicorn
import time
import logging
import os
import json
from dataclasses import dataclass
import pandas as pd

from agent.Utils.utils import *
from agent.Environment.html_env.async_env import AsyncHTMLEnvironment
from execute.execution import run_task, read_config
from agent.Utils.format_converter import format_converter

logger = logging.getLogger(__name__)
app = FastAPI()

class TaskRequest(BaseModel):
    global_reward_mode: str = "no_global_reward"
    planning_text_model: str = "gpt-4o"
    global_reward_text_model: str = "gpt-4o"
    task_name: str = "find blog posts on imean.ai"
    observation_mode: str = "dom"
    toml_path: str = "./inference/configs/setting.toml"
    input_parameters: Union[Dict[str, Any], List[Any], str] = Field(
        default={},
        description="Input parameters can be a dictionary, list, or string"
    )
    output_parameters: dict = {}
    response_type: str = "text"  # Can be "text", "list", "json", "number", "boolean", "table"
    browser_env: str = "local"  # Can be "local" or "browserbase"

@dataclass
class ExperimentConfig:
    mode: str
    global_reward_mode: str
    planning_model: str
    global_reward_text_model: str
    task_name: str
    config: dict
    write_result_file_path: str
    record_time: str
    browser_env: str

def validate_config(config, observation_mode, global_reward_mode, observation_model, global_reward_model):
    json_model_response = config['model']['json_model_response']
    all_json_models = config['model']['json_models']
    interaction_mode = config['steps']['interaction_mode']

    response_type = config.get("response_type", "text")
    allowed_types = ["text", "list", "json", "number", "boolean", "table"]
    if response_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"response_type must be one of: {', '.join(allowed_types)}"
        )

    if observation_mode not in ["dom", "vision"]:
        raise HTTPException(
            status_code=400,
            detail="observation mode is not correctly defined! Currently we only support DOM observation."
        )

    if interaction_mode not in [True, False]:
        raise HTTPException(
            status_code=400,
            detail="interaction_mode must be defined as boolean"
        )

    if json_model_response and (observation_model not in all_json_models or (
            global_reward_mode != 'no_global_reward' and global_reward_model not in all_json_models)):
        raise HTTPException(
            status_code=400,
            detail="Model does not support JSON mode!"
        )

def is_valid_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except:
        return False

def is_valid_table(text: str) -> bool:
    try:
        # Try parsing as DataFrame from various formats
        if isinstance(text, str):
            if text.strip().startswith('[') and text.strip().endswith(']'):
                # Try parsing as JSON array
                data = json.loads(text)
                pd.DataFrame(data)
                return True
            elif '|' in text:
                # Try parsing as markdown table
                pd.read_csv(pd.StringIO(text), sep='|', skipinitialspace=True)
                return True
        return False
    except:
        return False

def check_format(answer: Any, expected_type: str) -> bool:
    """Check if the answer matches the expected format"""
    if expected_type == "list":
        return isinstance(answer, list)
    elif expected_type == "json":
        if isinstance(answer, str):
            return is_valid_json(answer)
        return isinstance(answer, dict)
    elif expected_type == "number":
        try:
            float(str(answer))
            return True
        except:
            return False
    elif expected_type == "boolean":
        return isinstance(answer, bool)
    elif expected_type == "table":
        return isinstance(answer, (pd.DataFrame, list)) or is_valid_table(str(answer))
    elif expected_type == "text":
        return isinstance(answer, str)
    return False

def create_html_environment(mode, browser_env):
    return AsyncHTMLEnvironment(
        mode=mode,
        max_page_length=8192,
        headless=False,
        slow_mo=1000,
        current_viewport_only=False,
        viewport_size={"width": 1080, "height": 720},
        save_trace_enabled=False,
        sleep_after_execution=0.0,
        locale="en-US",
        use_vimium_effect=True,
        browser_env=browser_env
    )

class TaskResponse(BaseModel):
    status: str
    result: Dict[str, Any] = Field(
        default=None,
        description="Response result in a standardized format",
        example={
            "type": "text",  
            "value": "Some result", 
            "metadata": {  
                "format_version": "1.0",
                "timestamp": "2025-01-05T11:15:32"
            }
        }
    )
    error: Optional[str] = None
    token_cost: Optional[float] = None
    result_file_path: Optional[str] = None

async def run_experiment(experiment_config: ExperimentConfig) -> TaskResponse:
    env = create_html_environment(experiment_config.mode, experiment_config.browser_env)
    try:
        # Set up token tracking
        if not os.path.exists("token_results"):
            os.makedirs("token_results")
        token_counts_filename = f"token_results/token_counts_{experiment_config.record_time}_{experiment_config.planning_model}_{experiment_config.global_reward_text_model}.json"

        result = await run_task(
            mode=experiment_config.mode,
            task_mode="single_task",
            task_name=experiment_config.task_name,
            task_uuid=None,
            config=experiment_config.config,
            write_result_file_path=experiment_config.write_result_file_path,
            reference_task_length=experiment_config.config['steps']['single_task_action_step'],
            env=env,
            global_reward_mode=experiment_config.global_reward_mode,
            global_reward_text_model=experiment_config.global_reward_text_model,
            planning_model=experiment_config.planning_model,
            ground_truth_mode=False,
            ground_truth_data=None,
            interaction_mode=experiment_config.config['steps']['interaction_mode'],
            record_time=experiment_config.record_time,
            output_parameters=experiment_config.config["output_parameters"],
            response_type=experiment_config.config["response_type"]
        )
        
        # Add debug logging for initial result
        logger.info(f"Raw result from run_task: {str(result)}")
        logger.info(f"Result type: {type(result)}")

        if "status" in result and result["status"] == "incomplete":
            return TaskResponse(
                status="incomplete",
                result=result,
                token_cost=0
            )

        # 如果结果是字典类型，先转换为JSON字符串
        if isinstance(result, dict):
            result = json.dumps(result)
            
        # Check if the result matches the expected format
        if not check_format(result, experiment_config.config["response_type"]):
            result = await format_converter(result, experiment_config.config["response_type"], experiment_config.config["output_parameters"])
            logger.info(f"Result after format conversion: {result}")
            
        formatted_result = {
            "type": experiment_config.config["response_type"],
            "value": result,
            "metadata": {
                "format_version": "1.0",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        }
        logger.info(f"Final formatted result: {formatted_result}")

        # Calculate token costs
        total_token_cost = 0
        try:
            with open(token_counts_filename, 'r') as file:
                data = json.load(file)
            total_token_cost = data.get("total_token_cost", 0)
        except Exception as e:
            logger.warning(f"Failed to read token costs: {str(e)}")

        return TaskResponse(
            status="success",
            result=formatted_result,
            token_cost=total_token_cost
        )

    except Exception as e:
        error_msg = f"GUI agent failed: {str(e)}"
        logger.error(error_msg)
        return TaskResponse(
            status="error",
            error=error_msg
        )
    finally:
        await env.close()
        del env

async def execute_task(task_request: TaskRequest) -> TaskResponse:
    try:
        config = read_config(task_request.toml_path)
        config["response_type"] = task_request.response_type
        config["output_parameters"] = task_request.output_parameters
        config["input_parameters"] = task_request.input_parameters
        
        validate_config(
            config,
            task_request.observation_mode,
            task_request.global_reward_mode,
            task_request.planning_text_model,
            task_request.global_reward_text_model
        )

        record_time = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        write_result_file_path = "./output/json_result"

        experiment_config = ExperimentConfig(
            mode=task_request.observation_mode,
            global_reward_mode=task_request.global_reward_mode,
            planning_model=task_request.planning_text_model,
            global_reward_text_model=task_request.global_reward_text_model,
            task_name=task_request.task_name,
            config=config,
            write_result_file_path=write_result_file_path,
            record_time=record_time,
            browser_env=task_request.browser_env
        )

        return await run_experiment(experiment_config)

    except Exception as e:
        error_msg = f"Task execution failed: {str(e)}"
        logger.error(error_msg)
        return TaskResponse(
            status="error",
            error=error_msg
        )

@app.post("/execute", response_model=TaskResponse)
async def handle_execute(task_request: TaskRequest):
    return await execute_task(task_request)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
