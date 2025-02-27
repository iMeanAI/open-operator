from ..Utils.utils import print_info, print_limited_json
from agent.Prompt import *
from agent.LLM import *
from .action import *
import time
import json5
from .action import ResponseError
from logs import logger
from typing import Tuple


class InteractionMode:
    def __init__(self, text_model=None, visual_model=None):
        self.text_model = text_model
        self.visual_model = visual_model

    def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, output_parameters, response_type):
        pass


class DomMode(InteractionMode):
    def __init__(self, text_model=None, visual_model=None):
        super().__init__(text_model, visual_model)

    async def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, input_parameters, output_parameters, response_type):
        planning_request = PlanningPromptConstructor().construct(
            user_request, previous_trace, observation, feedback, status_description, input_parameters, output_parameters, response_type)
        logger.info(
            f"\033[32mDOM_based_planning_request:\n{planning_request}\033[0m\n")
        logger.info(f"planning_text_model: {self.text_model.model}")
        planning_response, error_message = await self.text_model.request(planning_request, max_tokens = 5000)
        input_token_count = calculation_of_token(planning_request, model=self.text_model.model)
        output_token_count = calculation_of_token(planning_response, model=self.text_model.model)
        planning_token_count = [input_token_count, output_token_count]

        return planning_response, error_message, None, None, planning_token_count


class DomVDescMode(InteractionMode):
    def __init__(self, text_model=None, visual_model=None):
        super().__init__(text_model, visual_model)

    async def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, output_parameters, response_type):
        if observation_VforD != "":
            vision_desc_request = VisionDisc2PromptConstructor().construct(
                user_request, observation_VforD, output_parameters, response_type)  # vision description request with user_request
            # vision_desc_request = VisionDisc1PromptConstructor().construct(observation_VforD)
            vision_desc_response, error_message = await self.visual_model.request(vision_desc_request)
        else:
            vision_desc_response = ""
        print(f"\033[36mvision_disc_response:\n{vision_desc_response}")  # blue
        planning_request = ObservationVisionDiscPromptConstructor().construct(
            user_request, previous_trace, observation, feedback, status_description, vision_desc_response)
        print(
            f"\033[35mplanning_request:\n{planning_request}")
        print("\033[0m")
        planning_response, error_message = await self.text_model.request(planning_request)
        return planning_response, error_message, None, None


class VisionToDomMode(InteractionMode):
    def __init__(self, text_model=None, visual_model=None):
        super().__init__(text_model, visual_model)

    async def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, output_parameters, response_type):
        vision_act_request = ObservationVisionActPromptConstructor().construct(
            user_request, previous_trace, observation_VforD, feedback, status_description, output_parameters, response_type)
        max_retries = 3
        for attempt in range(max_retries):
            vision_act_response, error_message = await self.visual_model.request(vision_act_request)
            # Blue output
            print(f"\033[36mvision_act_response:\n{vision_act_response}")
            print("\033[0m")  # Reset color
            planning_response_thought, planning_response_get = await ActionParser().extract_thought_and_action(
                vision_act_response)
            actions = {
                'goto': "Found 'goto' in the vision_act_response.",
                'google_search': "Found 'google_search' in the vision_act_response.",
                'switch_tab': "Found 'switch_tab' in the vision_act_response.",
                'scroll_down': "Found 'scroll_down' in the vision_act_response.",
                'scroll_up': "Found 'scroll_up' in the vision_act_response.",
                'go_back': "Found 'go_back' in the vision_act_response."
            }
            # Check if the action is in the predefined action list
            actions_found = False
            for action, message in actions.items():
                if action == planning_response_get.get('action'):
                    print(message)
                    actions_found = True
                    # The action does not need to be changed
                    # `target_element` should not exist, if it does, it's not used
                    break

            if not actions_found:
                print("None of 'goto', 'google_search', 'switch_tab', 'scroll_down', 'scroll_up', or 'go_back' were found in the vision_act_response.")

                target_element = planning_response_get.get('target_element')
                description = planning_response_get.get('description')

                # If the target element is None or does not exist
                if not target_element:
                    print("The 'target_element' is None or empty.")
                    continue

                # Construct the request from vision to DOM
                planning_request = VisionToDomPromptConstructor().construct(target_element, description,
                                                                            observation)
                print(f"\033[35mplanning_request:{planning_request}")
                print("\033[0m")

                # Send the request and wait for the response
                planning_response_dom, error_message = await self.text_model.request(planning_request)
                print(
                    f"\033[34mVisionToDomplanning_response:\n{planning_response_dom}")
                print("\033[0m")
                # Parse the element ID
                element_id = ActionParser().get_element_id(planning_response_dom)
                if element_id == "-1":
                    print("The 'element_id' is not found in the planning_response.")
                    continue  # If the 'element_id' is not found, continue to the next iteration of the loop
                else:
                    planning_response_get['element_id'] = element_id
                    break  # If the 'element_id' is found, break the loop

            else:
                # If a predefined action is found, there is no need to retry, exit the loop directly
                break

        planning_response_json_str = json5.dumps(
            planning_response_get, indent=2)
        planning_response = f'```\n{planning_response_json_str}\n```'
        # Check if the maximum number of retries has been reached
        if attempt == max_retries - 1:
            print("Max retries of vision_act reached. Unable to proceed.")

        return planning_response, error_message, planning_response_thought, planning_response_get


class DVMode(InteractionMode):
    def __init__(self, text_model=None, visual_model=None):
        super().__init__(text_model, visual_model)

    async def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, output_parameters, response_type):
        planning_request = D_VObservationPromptConstructor().construct(
            user_request, previous_trace, observation, observation_VforD, feedback, status_description, output_parameters, response_type)

        print(f"\033[32mplanning_request:\n{planning_request}")
        print("\033[0m")
        planning_response, error_message = await self.visual_model.request(planning_request, max_tokens = 5000)
        return planning_response, error_message, None, None


class VisionMode(InteractionMode):
    def __init__(self, text_model=None, visual_model=None):
        super().__init__(text_model, visual_model)

    async def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, input_parameters, output_parameters, response_type):
        planning_request = VisionObservationPromptConstructor(
        ).construct(user_request, previous_trace, observation, output_parameters, response_type)
        #print(f"\033[32m{planning_request}")  # Green color
        #print("\033[0m")
        logger.info("\033[32m%s\033[0m", planning_request)
        planning_response, error_message = await self.visual_model.request(planning_request)
        return planning_response, error_message, None, None, [0,0]  # 0,0 is the example token count
    
class VisionTestMode(InteractionMode):
    def __init__(self, text_model=None, visual_model=None):
        super().__init__(text_model, visual_model)

    async def execute(self, status_description, user_request, previous_trace, observation, feedback, observation_VforD, input_parameters, output_parameters, response_type):
        planning_response_click = """
        {
            "thought": "I need to click on the link that appears to lead to the submission dates for ACL 2025.",
            "action": "click",
            "action_input": "",
            "coordinates": {"x": 230, "y": 45},
            "description": "Click a Google search result to find the submission dates for ACL2025."
        }
        """
        planning_response_fill_search = """
        {
            "thought": "I need to fill in the submission dates for ACL 2025.",
            "action": "fill_search",
            "action_input": "AI",
            "coordinates": {"x": 330, "y": 250},
            "description": "Filling in the submission dates for ACL2025."   
        }
        """
        planning_response_hover = """
        {
            "thought": "I need to hover over the submission dates for ACL 2025.",
            "action": "hover",
            "action_input": "",
            "coordinates": {"x": 230, "y": 45},
            "description": "Hovering over the submission dates for ACL2025."
        }
        """
        planning_response_select = """
        {
            "thought": "I need to select the submission dates for ACL 2025.",
            "action": "select_option",
            "action_input": "",
            "coordinates": {"x": 460, "y": 230},
            "description": "Selecting the submission dates for ACL2025."
        }
        """
        planning_response = planning_response_fill_search
        return planning_response, "test error message", None, None, [0,0]


class Planning:

    @staticmethod
    async def plan(
        config,
        user_request,
        text_model_name,
        previous_trace,
        observation,
        feedback,
        mode,
        observation_VforD,
        status_description
    ):

        gpt35 = GPTGenerator(model="gpt-3.5-turbo")
        gpt4v = GPTGenerator(model="gpt-4-turbo")
        qwen2vl = create_llm_instance("Qwen/Qwen2-VL-72B-Instruct", False)
        llamavf = create_llm_instance("meta-llama/Llama-Vision-Free", False)
        llama3_90b = create_llm_instance("meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo", False)
        llama3_11b = create_llm_instance("meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo", False)
        

        all_json_models = config["model"]["json_models"]
        is_json_response = config["model"]["json_model_response"]

        llm_planning_text = create_llm_instance(
            text_model_name, is_json_response, all_json_models)
        modes = {
            "dom": DomMode(text_model=llm_planning_text),
            "dom_v_desc": DomVDescMode(visual_model=gpt4v, text_model=llm_planning_text),
            "vision_to_dom": VisionToDomMode(visual_model=gpt4v, text_model=llm_planning_text),
            "d_v": DVMode(visual_model=gpt4v),
            "vision": VisionTestMode(visual_model=llama3_90b)
        }

        # planning_response_thought, planning_response_action
        planning_response, error_message, planning_response_thought, planning_response_action, planning_token_count = await modes[mode].execute(
            status_description=status_description,
            user_request=user_request,
            previous_trace=previous_trace,
            observation=observation,
            feedback=feedback,
            observation_VforD=observation_VforD,
            input_parameters=config["input_parameters"],
            output_parameters=config["output_parameters"],
            response_type=config["response_type"]
        )

        logger.info(f"\033[34mPlanning_Response:\n{planning_response}\033[0m")
        if mode != "vision_to_dom":
            try:
                planning_response_thought, planning_response_action = await ActionParser().extract_thought_and_action(
                    planning_response, mode)
            except ResponseError as e:
                logger.error(f"Response Error:{e.message}")
                raise

        if planning_response_action.get('action') == "fill_form":
            JudgeSearchbarRequest = JudgeSearchbarPromptConstructor().construct(
                input_element=observation, planning_response_action=planning_response_action)
            try:
                Judge_response, error_message = await gpt35.request(JudgeSearchbarRequest)
                if Judge_response.lower() == "yes":
                    planning_response_action['action'] = "fill_search"  ### action里有link
            except:
                planning_response_action['action'] = "fill_form"

        # The description should include both the thought (returned by LLM) and the action (parsed from the planning response)
        planning_response_action["description"] = {
            "thought": planning_response_thought,
            "action": (
                f'{planning_response_action["action"]}: {planning_response_action["action_input"]}' if "description" not in planning_response_action.keys() else
                planning_response_action["description"])
        }
        if mode in ["dom", "d_v", "dom_v_desc", "vision_to_dom"]:
            planning_response_action = {element: planning_response_action.get(
                element, "") for element in ["element_id", "action", "action_input", "description"]}
        elif mode == "vision":
            planning_response_action = {element: planning_response_action.get(
                element, "") for element in ["coordinates", "action", "action_input", "description"]}
        logger.info("****************")
        # logger.info(planning_response_action)
        dict_to_write = {}
        if mode in ["dom", "d_v", "dom_v_desc", "vision_to_dom"]:
            dict_to_write['id'] = planning_response_action['element_id']
        elif mode == "vision":
            dict_to_write['coordinates'] = planning_response_action['coordinates']

        dict_to_write['action_type'] = planning_response_action['action']
        dict_to_write['value'] = planning_response_action['action_input']
        dict_to_write['description'] = planning_response_action['description']
        dict_to_write['error_message'] = error_message
        dict_to_write['planning_token_count'] = planning_token_count

        return dict_to_write
