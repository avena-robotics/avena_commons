#!/bin/bash
# filepath: /home/avena/avena_commons/script/stests/run_restore_terminals.sh

# Start a new tmux session
SESSION_NAME="restore_terminals"
tmux new-session -d -s $SESSION_NAME
# Define commands for each terminal
declare -A commands=(
    ["camera1"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_camera_listener.py --name camera1 --port 9000"
    ["camera2"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_camera_listener.py --name camera2 --port 9001"
    ["camera3"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_camera_listener.py --name camera3 --port 9002"
    ["camera4"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_camera_listener.py --name camera4 --port 9003"
    ["pepper1"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_listener.py pepper1 8001"
    ["pepper2"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_listener.py pepper2 8002"
    ["pepper3"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_listener.py pepper3 8003"
    ["pepper4"]="cd /home/avena/avena_commons && source .venv/bin/activate && python tests/pepper_listener.py pepper4 8004"
    ["load_images2"]="cd /home/avena/avena_commons && source .venv/bin/activate && taskset -c 7 python tests/load_images_listener.py pepper2 8002 3660"
    ["load_images3"]="cd /home/avena/avena_commons && source .venv/bin/activate && taskset -c 7 python tests/load_images_listener.py pepper3 8003 3660"
    ["load_images4"]="cd /home/avena/avena_commons && source .venv/bin/activate && taskset -c 7 python tests/load_images_listener.py pepper4 8004 3660"
    ["benchmark"]="cd /home/avena/avena_commons && source .venv/bin/activate && taskset -c 2 python tests/multi_camera_pepper_benchmark.py 600"
    ["htop"]="cd /home/avena/avena_commons && source .venv/bin/activate && htop"
)
# Create a new tmux window for each command
for name in "${!commands[@]}"; do
    tmux new-window -t $SESSION_NAME -n $name "${commands[$name]}"
done

# Attach to the tmux session
tmux attach-session -t $SESSION_NAME