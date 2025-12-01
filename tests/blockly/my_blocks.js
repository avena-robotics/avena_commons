// Definicje typów danych dla bloczków Vision
Blockly.Types['PhotoData'] = {
  'type': 'PhotoData',
  'message0': 'PhotoData',
  'colour': 120
};

Blockly.Types['CameraParams'] = {
  'type': 'CameraParams',
  'message0': 'CameraParams',
  'colour': 180
};

Blockly.Types['BGRImage'] = {
  'type': 'BGRImage',
  'message0': 'BGRImage',
  'colour': 180
};

Blockly.Types['DepthImage'] = {
  'type': 'DepthImage',
  'message0': 'DepthImage',
  'colour': 180
};

Blockly.Types['ColorMask'] = {
  'type': 'ColorMask',
  'message0': 'ColorMask',
  'colour': 160
};

Blockly.Types['FixedDepth'] = {
  'type': 'FixedDepth',
  'message0': 'FixedDepth',
  'colour': 160
};

Blockly.Types['DepthMask'] = {
  'type': 'DepthMask',
  'message0': 'DepthMask',
  'colour': 160
};

Blockly.Types['CombinedMask'] = {
  'type': 'CombinedMask',
  'message0': 'CombinedMask',
  'colour': 160
};

Blockly.Types['ProcessedMask'] = {
  'type': 'ProcessedMask',
  'message0': 'ProcessedMask',
  'colour': 160
};

Blockly.Types['UndistortedMask'] = {
  'type': 'UndistortedMask',
  'message0': 'UndistortedMask',
  'colour': 160
};

Blockly.Types['Contours'] = {
  'type': 'Contours',
  'message0': 'Contours',
  'colour': 160
};

Blockly.Types['FilteredContours'] = {
  'type': 'FilteredContours',
  'message0': 'FilteredContours',
  'colour': 160
};

Blockly.Types['EdgeFilteredContours'] = {
  'type': 'EdgeFilteredContours',
  'message0': 'EdgeFilteredContours',
  'colour': 160
};

Blockly.Types['InnerContours'] = {
  'type': 'InnerContours',
  'message0': 'InnerContours',
  'colour': 160
};

Blockly.Types['MinRectangle'] = {
  'type': 'MinRectangle',
  'message0': 'MinRectangle',
  'colour': 160
};

Blockly.Types['ValidationResult'] = {
  'type': 'ValidationResult',
  'message0': 'ValidationResult',
  'colour': 160
};

Blockly.Types['ImageOutput'] = {
  'type': 'ImageOutput',
  'message0': 'ImageOutput',
  'colour': 120
};

Blockly.Types['BoxOutput'] = {
  'type': 'BoxOutput',
  'message0': 'BoxOutput',
  'colour': 120
};

Blockly.Types['BoxDetectionResult'] = {
  'type': 'BoxDetectionResult',
  'message0': 'BoxDetectionResult',
  'colour': 200
};

// Definicje typów danych dla bloczków Vision
Blockly.Blocks['vision_take_photo'] = {
  init: function() {
    this.appendDummyInput()
        .appendField("zrób zdjęcie");
    this.setOutput(true, "PhotoData");
    this.setColour(120);
    this.setTooltip("Robienie zdjęcia z kamerą");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_camera_params'] = {
  init: function() {
    this.appendDummyInput()
        .appendField("parametry kamery");
    this.setOutput(true, "CameraParams");
    this.setColour(180);
    this.setTooltip("Parametry kamery");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_bgr_image'] = {
  init: function() {
    this.appendValueInput("PHOTO")
        .appendField("obraz BGR");
    this.setOutput(true, "BGRImage");
    this.setColour(180);
    this.setTooltip("Obraz BGR ze zdjęcia");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_depth_image'] = {
  init: function() {
    this.appendValueInput("PHOTO")
        .appendField("obraz głębi");
    this.setOutput(true, "DepthImage");
    this.setColour(180);
    this.setTooltip("Obraz głębi ze zdjęcia");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_create_color_mask'] = {
  init: function() {
    this.appendValueInput("BGR")
        .appendField("utwórz maskę koloru");
    this.setOutput(true, "ColorMask");
    this.setColour(160);
    this.setTooltip("Tworzy maskę na podstawie koloru");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_fix_depth'] = {
  init: function() {
    this.appendValueInput("DEPTH")
        .appendField("napraw głębię");
    this.setOutput(true, "FixedDepth");
    this.setColour(160);
    this.setTooltip("Naprawia obraz głębi");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_create_depth_mask'] = {
  init: function() {
    this.appendValueInput("DEPTH")
        .appendField("utwórz maskę głębi");
    this.setOutput(true, "DepthMask");
    this.setColour(160);
    this.setTooltip("Tworzy maskę na podstawie głębi");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_combine_masks'] = {
  init: function() {
    this.appendValueInput("COLOR_MASK")
        .appendField("połącz maski");
    this.appendValueInput("DEPTH_MASK");
    this.setOutput(true, "CombinedMask");
    this.setColour(160);
    this.setTooltip("Łączy maskę koloru i głębi");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_preprocess_mask'] = {
  init: function() {
    this.appendValueInput("MASK")
        .appendField("przetwórz maskę");
    this.setOutput(true, "ProcessedMask");
    this.setColour(160);
    this.setTooltip("Przetwarza połączoną maskę");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_undistort'] = {
  init: function() {
    this.appendValueInput("MASK")
        .appendField("usuń zniekształcenia");
    this.appendValueInput("CAMERA_PARAMS")
        .appendField("parametry");
    this.setOutput(true, "UndistortedMask");
    this.setColour(160);
    this.setTooltip("Usuwa zniekształcenia kamery");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_find_contours'] = {
  init: function() {
    this.appendValueInput("MASK")
        .appendField("znajdź kontury");
    this.setOutput(true, "Contours");
    this.setColour(160);
    this.setTooltip("Znajduje kontury w masce");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_remove_outside_contours'] = {
  init: function() {
    this.appendValueInput("CONTOURS")
        .appendField("usuń kontury poza pudełkiem");
    this.setOutput(true, "FilteredContours");
    this.setColour(160);
    this.setTooltip("Usuwa kontury poza obszarem pudełka");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_remove_edge_contours'] = {
  init: function() {
    this.appendValueInput("CONTOURS")
        .appendField("usuń kontury krawędzi");
    this.setOutput(true, "EdgeFilteredContours");
    this.setColour(160);
    this.setTooltip("Usuwa kontury dotykające krawędzi obrazu");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_find_inner_contours'] = {
  init: function() {
    this.appendValueInput("CONTOURS")
        .appendField("znajdź kontury wewnętrzne");
    this.setOutput(true, "InnerContours");
    this.setColour(160);
    this.setTooltip("Znajduje kontury wewnętrzne");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_create_min_rectangle'] = {
  init: function() {
    this.appendValueInput("CONTOURS")
        .appendField("utwórz prostokąt minimalny");
    this.setOutput(true, "MinRectangle");
    this.setColour(160);
    this.setTooltip("Tworzy prostokąt o minimalnym polu");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_validate_rectangle'] = {
  init: function() {
    this.appendValueInput("RECT")
        .appendField("sprawdź prostokąt");
    this.setOutput(true, "ValidationResult");
    this.setColour(160);
    this.setTooltip("Sprawdza czy prostokąt jest poprawny");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_prepare_image_output'] = {
  init: function() {
    this.appendValueInput("IMAGE")
        .appendField("przygotuj wyjście obrazu");
    this.setOutput(true, "ImageOutput");
    this.setColour(120);
    this.setTooltip("Przygotowuje obraz do wyjścia");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_prepare_box_output'] = {
  init: function() {
    this.appendValueInput("RECT")
        .appendField("przygotuj wyjście pudełka");
    this.setOutput(true, "BoxOutput");
    this.setColour(120);
    this.setTooltip("Przygotowuje dane pudełka do wyjścia");
    this.setHelpUrl("");
  }
};

Blockly.Blocks['vision_box_detection'] = {
  init: function() {
    this.appendValueInput("IMAGE")
        .appendField("detekcja pudełka");
    this.appendValueInput("DEPTH");
    this.appendValueInput("CAMERA_PARAMS");
    this.setOutput(true, "BoxDetectionResult");
    this.setColour(200);
    this.setTooltip("Kompletna procedura detekcji pudełka");
    this.setHelpUrl("");
  }
};

// Definicje bloczków w formacie JSON (alternatywna metoda)
Blockly.common.defineBlocksWithJsonArray([
    {
      "type": "io_load_image",
      "message0": "wczytaj obraz ścieżka %1",
      "args0": [
        { "type": "field_input", "name": "PATH", "text": "input.jpg" }
      ],
      "output": "Image",
      "colour": 210,
      "tooltip": "Wczytuje obraz z dysku"
    },
    {
      "type": "cv_canny",
      "message0": "Canny %1 próg1 %2 próg2 %3",
      "args0": [
        { "type": "input_value", "name": "IN", "check": "Image" },
        { "type": "field_number", "name": "T1", "value": 80, "min": 0, "max": 255 },
        { "type": "field_number", "name": "T2", "value": 160, "min": 0, "max": 255 }
      ],
      "output": "Image",
      "colour": 160,
      "tooltip": "Detekcja krawędzi"
    },
    {
      "type": "io_save_image",
      "message0": "zapisz obraz %1 ścieżka %2",
      "args0": [
        { "type": "input_value", "name": "IN", "check": "Image" },
        { "type": "field_input", "name": "PATH", "text": "out.png" }
      ],
      "previousStatement": null,
      "nextStatement": null,
      "colour": 210,
      "tooltip": "Zapisuje obraz na dysku"
    }
  ]);