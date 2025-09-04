import sys
import os

from openai import OpenAI

import pickle
import asyncio
from tqdm.autonotebook import tqdm, trange
import numpy as np

#TODO: Hard code this or set the path in the environment variable
#build_project_path = os.environ['BUILD_PROJECT_PATH']
build_project_path = r"C:\Users\L110006\OneDrive - Eli Lilly and Company\personal files\build project\fine-tuning-build-project"
synthetic_data_path = os.path.join(build_project_path, 'synthetic_data')

if synthetic_data_path not in sys.path:
    sys.path.append(synthetic_data_path)

from gpt_parsing import parse_gpt_response

#ori#data_path = os.path.join(build_project_path,'fine-tuning-build-project', 'synthetic_data', 'data')
data_path = os.path.join(build_project_path,'synthetic_data', 'data')

with open(os.path.join(data_path, 'initial_prompt.txt'), 'r') as f:
    base_prompt = f.read()

example_query_titles = []
with open(os.path.join(data_path, 'example_query_titles.txt'), 'r') as f:
    for line in f:
        example_query_titles.append(line.strip())

with open(os.path.join(data_path, 'example_assistant_response.txt'), 'r') as f:
    example_assistant_response = f.read()

with open(os.path.join(data_path, 'follow_up_prompt.txt'), 'r') as f:
    follow_up_prompt = f.read()

rng = np.random.default_rng()

# Set env var correctly (no trailing comma)
os.environ["SAMBANOVA_API_KEY"] = "f92f994d-86bb-454e-984d-8182b361594f"

def get_client():
    return OpenAI(
        api_key = "829993a9-ff57-414c-912d-58212968888b",
        #api_key=os.environ["SAMBANOVA_API_KEY"],
        base_url="https://api.sambanova.ai/v1",
    )

#def get_client():
#    return OpenAI(
#        # TODO: Make sure this API key is set in the environment variable (best not to hard code it)
#        SAMBANOVA_API_KEY = "829993a9-ff57-414c-912d-58212968888b",
#        # api_key=os.environ["8841f010-0daa-4701-bdaf-89937409bac7"],
#        api_key=os.environ["SAMBANOVA_API_KEY"],
#        base_url="https://api.sambanova.ai/v1",
#    )

def format_query_title_list(query_job_titles):
    output_string = ''
    for i, title in enumerate(query_job_titles):
        output_string += f'{i+1}. `{title}`\n'
    return output_string
    
def generate_prompt(query_job_titles : list[str] | np.ndarray, num_examples_per_title=5):
    # Spoofing the assistant response to encourage a certain format
    return [
        {"role": "system", "content": "You are an expert in recruitment, staffing and HR."},
        {"role": "user", "content": f"{base_prompt.format(format_query_title_list(example_query_titles))}"},
        {"role": "assistant", "content": example_assistant_response},
        {"role": "user", "content": f"{follow_up_prompt.format(num_examples_per_title, format_query_title_list(query_job_titles))}"},
    ]

async def async_make_api_call(client, model_name, messages, perturbation_std=0.0):
    # Adding perturbation to the temperature to avoid cached responses (I actually think they patched this away unfortunately!!)
    response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            stop=["<query>"],
            temperature=0.7 + rng.normal(0, perturbation_std)
        )
    return response


async def async_main_stubborn(all_query_titles, client, model_name, output_path=None, chunk_size=2, num_examples_per_title=2, delay=2, giveup_after=10):

    responses_dict = {}
    for i in trange(0, len(all_query_titles), chunk_size):
        attempts = 0
        current_query_titles = all_query_titles[i:i+chunk_size]
        while attempts < giveup_after:
            if attempts > 0:
                print(f'Attempt {attempts} for chunk {i // chunk_size}')
            api_task = asyncio.create_task(
                async_make_api_call(
                    client,
                    model_name,
                    generate_prompt(
                        query_job_titles=current_query_titles,
                        num_examples_per_title=num_examples_per_title
                    ),
                    perturbation_std=0.1
                )
            )
            await asyncio.sleep(delay)
            response = await api_task
            parsed_response = parse_gpt_response(
                gpt_output=response.choices[0].message.content,
                num_query_titles=chunk_size,
                num_examples_per_query_title=num_examples_per_title,
                throw_exception_on_failure=False
            )
            if parsed_response:
                for query_title, response_list in zip(current_query_titles, parsed_response):
                    responses_dict[query_title] = response_list
                break
            elif attempts > 2:
                print('-------------------------------')
                print('Output:')
                print(response.choices[0].message.content)
            attempts += 1

        if output_path:
            with open(output_path, 'wb') as f:
                pickle.dump(responses_dict, f)

    return responses_dict