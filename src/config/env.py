import os

from src.config.global_config import ROOT_DIR

root_path = ROOT_DIR
log_path = os.path.join(root_path, "log")
conf_path = os.path.join(root_path, "config")
data_path = os.path.join(root_path, "data")

if __name__ == "__main__":
    print(root_path)
    print(log_path)
    print(conf_path)
    print(data_path)
