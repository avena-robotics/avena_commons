// Import cv2 tylko raz na górze pliku
Blockly.Python.definitions_['import_cv2'] = 'import cv2';

Blockly.Python['io_load_image'] = function(block) {
  const path = block.getFieldValue('PATH');
  const code = `cv2.imread("${path}")`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['cv_canny'] = function(block) {
  const input = Blockly.Python.valueToCode(block, 'IN', Blockly.Python.ORDER_NONE) || 'None';
  const t1 = block.getFieldValue('T1');
  const t2 = block.getFieldValue('T2');
  const code = `cv2.Canny(${input}, ${t1}, ${t2})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['io_save_image'] = function(block) {
  const input = Blockly.Python.valueToCode(block, 'IN', Blockly.Python.ORDER_NONE) || 'None';
  const path = block.getFieldValue('PATH');
  return `cv2.imwrite("${path}", ${input})\n`;
};

// Generatory kodu dla bloczków Vision
Blockly.Python['vision_take_photo'] = function(block) {
  return ['take_photo()', Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_camera_params'] = function(block) {
  return ['get_camera_params()', Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_bgr_image'] = function(block) {
  const photo = Blockly.Python.valueToCode(block, 'PHOTO', Blockly.Python.ORDER_NONE) || 'None';
  const code = `get_bgr_image(${photo})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_depth_image'] = function(block) {
  const photo = Blockly.Python.valueToCode(block, 'PHOTO', Blockly.Python.ORDER_NONE) || 'None';
  const code = `get_depth_image(${photo})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_create_color_mask'] = function(block) {
  const bgr = Blockly.Python.valueToCode(block, 'BGR', Blockly.Python.ORDER_NONE) || 'None';
  const code = `create_color_mask(${bgr})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_fix_depth'] = function(block) {
  const depth = Blockly.Python.valueToCode(block, 'DEPTH', Blockly.Python.ORDER_NONE) || 'None';
  const code = `fix_depth(${depth})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_create_depth_mask'] = function(block) {
  const depth = Blockly.Python.valueToCode(block, 'DEPTH', Blockly.Python.ORDER_NONE) || 'None';
  const code = `create_depth_mask(${depth})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_combine_masks'] = function(block) {
  const colorMask = Blockly.Python.valueToCode(block, 'COLOR_MASK', Blockly.Python.ORDER_NONE) || 'None';
  const depthMask = Blockly.Python.valueToCode(block, 'DEPTH_MASK', Blockly.Python.ORDER_NONE) || 'None';
  const code = `combine_masks(${colorMask}, ${depthMask})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_preprocess_mask'] = function(block) {
  const mask = Blockly.Python.valueToCode(block, 'MASK', Blockly.Python.ORDER_NONE) || 'None';
  const code = `preprocess_mask(${mask})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_undistort'] = function(block) {
  const mask = Blockly.Python.valueToCode(block, 'MASK', Blockly.Python.ORDER_NONE) || 'None';
  const cameraParams = Blockly.Python.valueToCode(block, 'CAMERA_PARAMS', Blockly.Python.ORDER_NONE) || 'None';
  const code = `undistort(${mask}, ${cameraParams})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_find_contours'] = function(block) {
  const mask = Blockly.Python.valueToCode(block, 'MASK', Blockly.Python.ORDER_NONE) || 'None';
  const code = `find_contours(${mask})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_remove_outside_contours'] = function(block) {
  const contours = Blockly.Python.valueToCode(block, 'CONTOURS', Blockly.Python.ORDER_NONE) || 'None';
  const code = `remove_outside_contours(${contours})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_remove_edge_contours'] = function(block) {
  const contours = Blockly.Python.valueToCode(block, 'CONTOURS', Blockly.Python.ORDER_NONE) || 'None';
  const code = `remove_edge_contours(${contours})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_find_inner_contours'] = function(block) {
  const contours = Blockly.Python.valueToCode(block, 'CONTOURS', Blockly.Python.ORDER_NONE) || 'None';
  const code = `find_inner_contours(${contours})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_create_min_rectangle'] = function(block) {
  const contours = Blockly.Python.valueToCode(block, 'CONTOURS', Blockly.Python.ORDER_NONE) || 'None';
  const code = `create_min_area_rectangle(${contours})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_validate_rectangle'] = function(block) {
  const rect = Blockly.Python.valueToCode(block, 'RECT', Blockly.Python.ORDER_NONE) || 'None';
  const code = `validate_rectangle(${rect})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_prepare_image_output'] = function(block) {
  const image = Blockly.Python.valueToCode(block, 'IMAGE', Blockly.Python.ORDER_NONE) || 'None';
  const code = `prepare_image_output(${image})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_prepare_box_output'] = function(block) {
  const rect = Blockly.Python.valueToCode(block, 'RECT', Blockly.Python.ORDER_NONE) || 'None';
  const code = `prepare_box_output(${rect})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Python['vision_box_detection'] = function(block) {
  const image = Blockly.Python.valueToCode(block, 'IMAGE', Blockly.Python.ORDER_NONE) || 'None';
  const depth = Blockly.Python.valueToCode(block, 'DEPTH', Blockly.Python.ORDER_NONE) || 'None';
  const cameraParams = Blockly.Python.valueToCode(block, 'CAMERA_PARAMS', Blockly.Python.ORDER_NONE) || 'None';
  const code = `detect_box(${image}, ${depth}, ${cameraParams})`;
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};
