import cv2
import numpy as np

#MARK: IMAGE CROP

def image_crop(depth, params):
    """
    Crop the input depth image based on the specified parameters.

    Args:
        depth (numpy.ndarray): The input depth image.
        params (dict): A dictionary containing the crop parameters.

    Returns:
        numpy.ndarray: The cropped depth image.
    """
    depth_crop = depth[params['crop_y'][0]:params['crop_y'][1], params['crop_x'][0]:params['crop_x'][1]]
    return depth_crop

#MARK: WHITE PERCENTAGE IN MASK

def get_white_percentage_in_mask(rgb, mask, hsv_range):
    debug = {}

    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
    debug["hsv"] = hsv
    higher_range = np.array(hsv_range[1])
    lower_range = np.array(hsv_range[0])
    mask_in_range = cv2.inRange(hsv, lower_range, higher_range)
    
    # hsl = cv2.cvtColor(rgb, cv2.COLOR_BGR2HLS)
    # debug["hsv"] = hsl
    # higher_range_hsl = np.array([180, 75, 255])
    # lower_range_hsl = np.array([0, 0, 200])
    # mask_in_range = cv2.inRange(hsl, lower_range_hsl, higher_range_hsl)
    
    debug["mask_in_range"] = mask_in_range
    mask_in_range_in_mask = mask_in_range[mask == 255]
    mask_in_range_non_zero = mask_in_range_in_mask[mask_in_range_in_mask > 0]
    
    if len(mask_in_range_in_mask.flatten()) == 0:
        return 0, debug
    
    white_percentage = len(mask_in_range_non_zero) / len(mask_in_range_in_mask.flatten())
    return white_percentage, debug

#MARK: MASK REFINMENT
def pepper_mask_refinement(mask, params):
    debug = {}
    
    # 🔍 DEBUG: Informacje o refinement
    print(f"🧹 PEPPER_MASK_REFINEMENT DEBUG:")
    print(f"   Input mask pixels: {np.count_nonzero(mask)}")
    
    kernel_open = params["mask_de_noise_open_params"]["kernel"]
    iterations_open = params["mask_de_noise_open_params"]["iterations"]
    kernel_close = params["mask_de_noise_close_params"]["kernel"]
    iterations_close = params["mask_de_noise_close_params"]["iterations"]
    min_area = params["min_mask_area"]
    
    print(f"   Open kernel: {kernel_open}, iterations: {iterations_open}")
    print(f"   Close kernel: {kernel_close}, iterations: {iterations_close}")
    print(f"   Min area threshold: {min_area}")
    
    mask_without_noise = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones(kernel_open, np.uint8), iterations=iterations_open)
    print(f"   After OPEN: {np.count_nonzero(mask_without_noise)} pixels")
    
    mask_without_noise = cv2.morphologyEx(mask_without_noise, cv2.MORPH_CLOSE, np.ones(kernel_close, np.uint8), iterations=iterations_close)
    print(f"   After CLOSE: {np.count_nonzero(mask_without_noise)} pixels")
    
    debug['mask_without_noise'] = mask_without_noise
    
    contours, _ = cv2.findContours((mask_without_noise), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"   Contours found: {len(contours)}")
    
    pepper_contour = None
    valid_contours = 0
    # 🔧 POPRAWKA: Dynamiczny punkt środkowy dla różnych rozmiarów ROI
    image_height, image_width = mask.shape[:2]
    center_point = (image_width // 2, image_height // 2)
    print(f"   Image size: {image_width}x{image_height}, center point: {center_point}")
    
    for idx, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        result = cv2.pointPolygonTest(contour, center_point, True) #POPRAWIONE: używa dynamicznego środka
        print(f"     Contour {idx}: area={area:.1f}, distance_to_center={result:.1f}")
        
        if area > min_area: #TODO: param
            print(f"       Area OK ({area:.1f} > {min_area})")
            # 🔧 POPRAWKA: Zwiększona tolerancja distance dla małych ROI
            distance_threshold = -20  # Było -5, teraz bardziej tolerancyjne
            if result > distance_threshold:
                print(f"       Distance OK ({result:.1f} > {distance_threshold}) - CONTOUR ACCEPTED")
                pepper_contour = contour
                valid_contours += 1
                break
            else:
                print(f"       Distance NOT OK ({result:.1f} <= {distance_threshold}) - CONTOUR REJECTED")
        else:
            print(f"       Area TOO SMALL ({area:.1f} <= {min_area}) - CONTOUR REJECTED")
    
    pepper_mask = np.zeros_like(mask)
    
    if pepper_contour is not None:
        cv2.fillPoly(pepper_mask, [pepper_contour], 255)
        print(f"   ✅ FINAL PEPPER MASK: {np.count_nonzero(pepper_mask)} pixels")
    else:
        print(f"   ❌ NO VALID PEPPER CONTOUR FOUND - empty mask")
    
    debug['pepper_mask'] = pepper_mask
    print(f"🧹 PEPPER_MASK_REFINEMENT DEBUG END\n")
    
    return pepper_mask, debug

#MARK: CONVEX HULL MASK

def convex_hull_mask(mask):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if len(contours) == 0: return None
    
    all_contours = np.vstack([contours[i] for i in range(len(contours))])

    hull = cv2.convexHull(all_contours)
    
    mask_hull = np.zeros_like(mask)
    cv2.fillPoly(mask_hull, [hull], 255)
    
    return mask_hull

#MARK: JOINED MASKS HULL

def convex_hull_joined_masks(mask_1, mask_2):
    contours, _ = cv2.findContours(mask_1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if len(contours) == 0:
        return None

    all_contours = np.vstack([contours[i] for i in range(len(contours))])
    hull_1 = cv2.convexHull(all_contours)
    
    contours, _ = cv2.findContours(mask_2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if len(contours) == 0:
        return None
    
    all_contours = np.vstack([contours[i] for i in range(len(contours))])
    hull_2 = cv2.convexHull(all_contours)
    
    joined_mask = np.zeros_like(mask_1)
    cv2.fillPoly(joined_mask, [hull_1, hull_2], 255)
    
    return joined_mask


#MARK: REFINE HOLE MASK WITH DEPTH
def refine_hole_mask_with_depth(hole_mask, pepper_mask, depth):
    debug = {}

    near_hole_mask = cv2.dilate(hole_mask, np.ones((5, 5), np.uint8), iterations=1) #TODO: param kernel 
    far_hole_mask = cv2.dilate(hole_mask, np.ones((5, 5), np.uint8), iterations=4) #TODO: param kernel

    strip_mask = cv2.bitwise_xor(near_hole_mask, far_hole_mask)

    strip_mask = cv2.bitwise_and(strip_mask, pepper_mask)
    debug['strip_mask'] = strip_mask
    
    depth_in_pepper = depth[strip_mask == 255]
    depth_in_pepper_non_zero = depth_in_pepper[depth_in_pepper > 0]
    depth_mean = np.mean(depth_in_pepper_non_zero)

    debug["depth_mean"] = depth_mean
    #Depth mask 255 is when the depth is depth_mean and less otherwise 0
    depth_mask = np.zeros_like(depth, dtype=np.uint8)
    depth_mask[depth > depth_mean] = 255

    debug['depth_mask'] = depth_mask

    new_hole_mask = cv2.bitwise_and(hole_mask, depth_mask)
    
    excluded_mask = hole_mask - new_hole_mask

    return new_hole_mask, excluded_mask, debug


#MARK: MASK EDGE AREA

def get_mask_edge_area(mask):
    edge_area = (mask - cv2.erode(mask, np.ones((8, 8), np.uint8), iterations=3)) #*255 #TODO: param kernel, iterations
    return edge_area

#MARK: FILTER EXCLUSION MASK
def filter_exclusion_mask(mask, exclusion_mask):
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(exclusion_mask))
    return mask

#MARK: ADD EXCLUSION MASKS
def add_exclusion_masks(exclusion_masks):
    mask = np.zeros_like(exclusion_masks[0])
    for exclusion_mask in exclusion_masks:
        mask = cv2.bitwise_or(mask, exclusion_mask)
    return mask

#MARK: ADD NOZZLE_MASK
def add_nozzle_mask(mask, nozzle_mask):
    mask = cv2.bitwise_or(mask, nozzle_mask)
    return mask

#MARK: NOZZLE VECTOR
def nozzle_vector(nozzle_mask):

    nozzle_mask[:,:40] = 0
    nozzle_mask[:,140:] = 0
    contours, _ = cv2.findContours(nozzle_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) == 0:
        return None
    
    
    cnt = max(contours, key=cv2.contourArea)
    M = cv2.moments(cnt)
    cx = int(M['m10']/M['m00'])
    cy = int(M['m01']/M['m00'])
    
    if M['mu20'] != M['mu02']:
        angle = 0.5 * np.arctan((2 * M['mu11']) / (M['mu20'] - M['mu02']))
    else:
        angle = np.pi / 2
    
    # Convert angle to vector (assuming unit length for simplicity)
    vector_x = np.cos(angle)
    vector_y = np.sin(angle)
    
    new_vector_x = -vector_y
    new_vector_y = vector_x
    
    vector_x = new_vector_x
    vector_y = new_vector_y
        
    return vector_x, vector_y, cx, cy


#MARK: CREATE SEED MASK
def create_seed_masks(image_rgb, params):

    debug = {}
    
    seed_config = params["seed_removal_config"]
    hsv_range = seed_config["hsv_range"]
    rgb_range = seed_config["rgb_range"]
    hsv_close_1_params = seed_config["hsv_close_1_params"]
    hsv_dilate_params = seed_config["hsv_dilate_params"]
    hsv_open_params = seed_config["hsv_open_params"]
    hsv_close_2_params = seed_config["hsv_close_2_params"]
    rgb_dilate_params = seed_config["rgb_dilate_params"]
    rgb_close_1_params = seed_config["rgb_close_1_params"]
    rgb_close_2_params = seed_config["rgb_close_2_params"]
    rgb_close_3_params = seed_config["rgb_close_3_params"]

    #HSV MASK
    lower_color_hsv= np.array(hsv_range[0])
    upper_color_hsv = np.array(hsv_range[1])

    image_hsv = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2HSV)
    mask_hsv = cv2.inRange(image_hsv, lower_color_hsv, upper_color_hsv)
    
    #MORPH CLUSTER
    
    #mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_DILATE,(np.ones((3,3),np.uint8)))
    #mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_OPEN,(np.ones((5,5),np.uint8)))
    #mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_CLOSE,(np.ones((2,2),np.uint8)))
    
    mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_CLOSE, (np.ones(hsv_close_1_params["kernel"],np.uint8)))
    mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_DILATE,(np.ones(hsv_dilate_params["kernel"],np.uint8)))
    mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_OPEN,(np.ones(hsv_open_params["kernel"],np.uint8)))
    mask_hsv = cv2.morphologyEx(mask_hsv, cv2.MORPH_CLOSE,(np.ones(hsv_close_2_params["kernel"],np.uint8)))
    
    debug['mask_hsv'] = mask_hsv

    # lower_color_rgb = np.array([151, 104, 14])
    # upper_color_rgb = np.array([209, 164, 87])
    lower_color_rgb = np.array(rgb_range[0])
    upper_color_rgb = np.array(rgb_range[1])

    mask_rgb = cv2.inRange(image_rgb, lower_color_rgb, upper_color_rgb)
    
    # mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_DILATE, np.ones((3,3),np.uint8))
    # mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_CLOSE, np.ones((7,7),np.uint8))
    # mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_CLOSE, np.ones((9,9),np.uint8))
    # mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_CLOSE, np.ones((2,2),np.uint8))
    
    mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_DILATE, np.ones((rgb_dilate_params["kernel"]), np.uint8))
    mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_CLOSE, np.ones((rgb_close_1_params["kernel"]), np.uint8))
    mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_CLOSE, np.ones((rgb_close_2_params["kernel"]), np.uint8))
    mask_rgb = cv2.morphologyEx(mask_rgb, cv2.MORPH_CLOSE, np.ones((rgb_close_3_params["kernel"]), np.uint8))

    debug['mask_rgb'] = mask_rgb

    seed_mask = cv2.bitwise_or(mask_hsv, mask_rgb)

    return seed_mask, debug

#NOZZLE IN PEPPER MASK

def nozzle_in_pepper_mask(rgb, nozzle_mask, pepper_mask, section_select):
    # 🔍 DODANE: Szczegółowe informacje debug
    print(f"🔍 NOZZLE_IN_PEPPER_MASK DEBUG:")
    print(f"   Section: {section_select}")
    print(f"   RGB shape: {rgb.shape}")
    print(f"   Nozzle mask non-zero pixels: {np.count_nonzero(nozzle_mask)}")
    print(f"   Pepper mask non-zero pixels: {np.count_nonzero(pepper_mask)}")
    
    masked_nozzle = cv2.bitwise_and(rgb, rgb, mask=nozzle_mask)
    masked_nozzle = cv2.bitwise_and(masked_nozzle, masked_nozzle, mask=pepper_mask)
    
    print(f"   Masked nozzle non-zero pixels: {np.count_nonzero(masked_nozzle)}")

    canny = cv2.Canny(masked_nozzle, 100, 200)
    canny = cv2.morphologyEx(canny, cv2.MORPH_DILATE, np.ones((3, 3), np.uint8))
    
    print(f"   Canny edges found: {np.count_nonzero(canny)} pixels")
    
    canny_contour, _ = cv2.findContours(canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"   External contours found: {len(canny_contour)}")
    
    if len(canny_contour) > 0:
        canny_area = cv2.contourArea(canny_contour[0])
        print(f"   Largest external contour area: {canny_area}")
    else:
        print("   ❌ NO EXTERNAL CONTOURS FOUND - returning empty mask")
        final_mask = np.zeros_like(nozzle_mask)
        return final_mask
    #canny_copy = canny.copy()

    black = np.zeros_like(canny)
    black = cv2.cvtColor(black, cv2.COLOR_GRAY2BGR)
    
    contours,_ = cv2.findContours(canny, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    internal_contours = []
    hierarchy = _[0]
    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1:
            internal_contours.append(contour)
    
    print(f"   Internal contours found: {len(internal_contours)}")
    
    min_distance = -100000
    closest_contour = None
    point = None

    section = section_select
    match section:
        case "bottom_right":    point = (0,0)
        case "bottom_left":     point = (180,0)
        case "top_right":       point = (0,180)
        case "top_left":        point = (180,180)
    
    print(f"   Reference point for section '{section}': {point}")

    if len(internal_contours) > 0:
        print(f"   Analyzing {len(internal_contours)} internal contours:")
        for idx, contour in enumerate(internal_contours):
            area = cv2.contourArea(contour)
            distance = cv2.pointPolygonTest(contour, (point[0], point[1]), True)
            print(f"     Contour {idx}: area={area:.1f}, distance_to_point={distance:.1f}")
            if distance > min_distance:
                min_distance = distance
                closest_contour = contour
    
        if closest_contour is not None:
            cv2.drawContours(black, [closest_contour], -1, (255, 0, 0), 1)
            contour_area = cv2.contourArea(closest_contour)
            
            print(f"   Selected closest contour: area={contour_area:.1f}, min_distance={min_distance:.1f}")
            print(f"   Area threshold (0.4 * canny_area): {0.4*canny_area:.1f}")
            
            final_mask = None

            if contour_area < 0.4*canny_area:
                print(f"   ✅ CONTOUR ACCEPTED (area {contour_area:.1f} < {0.4*canny_area:.1f})")
                final_mask = np.zeros_like(nozzle_mask)
                cv2.fillPoly(final_mask, [closest_contour], (255, 255, 255))
                # final_mask = black
            else: 
                print(f"   ❌ CONTOUR REJECTED - TOO LARGE (area {contour_area:.1f} >= {0.4*canny_area:.1f})")
                print("No contour found")
                final_mask = np.zeros_like(nozzle_mask)
                # final_mask = cv2.cvtColor(final_mask, cv2.COLOR_BGR2GRAY)
        else:
            print(f"   ❌ NO CLOSEST CONTOUR FOUND")
            print("No contour found") 
            final_mask = np.zeros_like(nozzle_mask)
    else:
        print(f"   ❌ NO INTERNAL CONTOURS FOUND")
        print("No contour found")
        final_mask = np.zeros_like(nozzle_mask)
        # final_mask = cv2.cvtColor(final_mask, cv2.COLOR_BGR2GRAY)

    print(f"   Final mask non-zero pixels: {np.count_nonzero(final_mask)}")
    print(f"🔍 NOZZLE_IN_PEPPER_MASK DEBUG END\n")
    return final_mask