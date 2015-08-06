
function clear_manager {
    python $BASE_DIR/tests/utils/clear_manager.py
}

function create_inputs {
    python $BASE_DIR/tests/utils/create_inputs.py $1 261844b3-479c-5446-a2c4-1ea95d53b668 102 ubuntu
}
