# 12.11.24

# Fix import
import os
import sys
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(src_path)


# Other
import time
import json
from rich.console import Console


# Util
from StreamingCommunity.Util._jsonConfig import config_manager
from StreamingCommunity.Api.Template.Util import search_domain


# Variable
console = Console()
README_PATH = "README.md"


def get_config():
    with open("config.json", "r", encoding="utf-8") as file:
        return json.load(file)
    

def update_readme(site_names, domain_to_use):
    if not os.path.exists(README_PATH):
        console.print(f"[red]README file not found at {README_PATH}")
        return

    with open(README_PATH, "r", encoding="utf-8") as file:
        lines = file.readlines()

    updated_lines = []

    for line in lines:
        if line.startswith("| [") and "|" in line:
            site_name = line.split("[")[1].split("]")[0]
            alias = f"{site_name.lower()}"

            if alias in site_names:
                command = f"-{site_name[:3].upper()}"

                if site_name == "animeunity":
                    updated_line = f"| [{site_name}](https://www.{alias}.{domain_to_use}/) |   ✅   | {command} |\n"
                else:
                    updated_line = f"| [{site_name}](https://{alias}.{domain_to_use}/) |   ✅   | {command} |\n"

                updated_lines.append(updated_line)
                continue

        updated_lines.append(line)

    with open(README_PATH, "w", encoding="utf-8") as file:
        file.writelines(updated_lines)


if __name__ == "__main__":
    for site_name, data in get_config()['SITE'].items():
        original_domain = config_manager.get_dict("SITE", site_name)['domain']

        if site_name != "ilcorsaronero":
            if site_name == "animeunity":
                domain_to_use, _ = search_domain(site_name, f"https://www.{site_name}.{original_domain}", True)
            else:
                domain_to_use, _ = search_domain(site_name, f"https://{site_name}.{original_domain}", True)
                
            update_readme(site_name, domain_to_use)
            print("\n------------------------------------")
            time.sleep(1)