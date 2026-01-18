import os

current_path = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.dirname(current_path)
root_path = os.path.dirname(src_path)
log_path = os.path.join(root_path, 'log')
conf_path = os.path.join(root_path, 'config')
data_path = os.path.join(root_path, 'data')

if __name__ == "__main__":
    print(root_path)
    print(src_path)
    print(log_path)
    print(conf_path)
    print(data_path)