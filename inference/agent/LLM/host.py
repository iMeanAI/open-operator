import os
import sys
import asyncio
from functools import partial
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from sanic.log import logger
from transformers import AutoProcessor, AutoModelForCausalLM, TextIteratorStreamer
from proxy_lite.tools import ReturnValueTool, BrowserTool
from proxy_lite.serializer import OpenAICompatableSerializer
from qwen_vl_utils import process_vision_info
import torch
from threading import Thread

class ProxyLiteGenerator:
    def __init__(self, model="convergence-ai/proxy-lite-3b"):
        self.model = model
        self.pool = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = None
        self.model_instance = None
        self.serializer = OpenAICompatableSerializer()
    
    async def request(self, messages: list = None, max_tokens: int = 500, temperature: float = 0.7) -> (str, str):
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                self.pool, 
                partial(self.chat, messages, max_tokens, temperature)
            )
            return response, ""
        except Exception as e:
            logger.error(f"Error in ProxyLiteGenerator.request: {e}")
            return "", str(e)
    
    def chat(self, messages, max_tokens=500, temperature=0.7):
        # 如果模型尚未加载，则加载模型
        if self.processor is None or self.model_instance is None:
            try:
                self.processor = AutoProcessor.from_pretrained(self.model)
                self.model_instance = AutoModelForCausalLM.from_pretrained(
                    self.model,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    device_map=self.device
                )
                logger.info(f"Model {self.model} loaded successfully on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                return f"Error loading model: {str(e)}"
        
        try:
            tools = self.serializer.serialize_tools([ReturnValueTool(), BrowserTool(session=None)])
            
            templated_messages = self.processor.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=True, 
                tools=tools
            )
            
            image_inputs, video_inputs = process_vision_info(messages)
            
            batch = self.processor(
                text=[templated_messages],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )
            
            for k, v in batch.items():
                if hasattr(v, "to"):
                    batch[k] = v.to(self.device)
            
            streamer = TextIteratorStreamer(
                self.processor.tokenizer, 
                timeout=10.0, 
                skip_prompt=True,
                skip_special_tokens=True
            )
            
            generation_kwargs = dict(
                input_ids=batch["input_ids"],
                attention_mask=batch.get("attention_mask", None),
                streamer=streamer,
                max_new_tokens=max_tokens,
                do_sample=temperature > 0,
                temperature=temperature,
                top_p=0.95,
                top_k=50,
                repetition_penalty=1.1
            )
            
            # 在单独的线程中运行生成过程
            thread = Thread(target=self.model_instance.generate, kwargs=generation_kwargs)
            thread.start()
            
            # 收集生成的文本
            generated_text = ""
            for text in streamer:
                generated_text += text
            
            thread.join()
            
            return generated_text.strip()
            
        except Exception as e:
            logger.error(f"Error in chat processing: {e}")
            return f"Error processing chat: {str(e)}"