# shops/utils.py
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim

def get_decimal_from_dms(dms, ref):
    degrees = dms[0]
    minutes = dms[1] / 60.0
    seconds = dms[2] / 3600.0
    decimal = degrees + minutes + seconds
    if ref in ['S', 'W']:
        decimal = -decimal
    return decimal

def get_clean_address(location):
    if not location:
        return ""
    addr = location.raw.get('address', {})
    parts = []
    
    # Lấy các thành phần địa chỉ quan trọng
    if 'road' in addr: parts.append(addr['road'])
    
    ward = addr.get('quarter') or addr.get('ward') or addr.get('village')
    if ward: parts.append(ward)

    district = addr.get('city_district') or addr.get('district') or addr.get('county') or addr.get('suburb')
    if district: parts.append(district)

    city = addr.get('city') or addr.get('state')
    if city: parts.append(city)

    return ", ".join(parts)

def extract_gps_data(image_file):
    """
    Hàm này chỉ đọc file, trả về toạ độ và địa chỉ, KHÔNG LƯU DATABASE
    """
    try:
        image = Image.open(image_file)
        exif_data = image._getexif()

        if not exif_data:
            return None

        gps_info = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            if tag_name == "GPSInfo":
                for key in value.keys():
                    sub_tag = GPSTAGS.get(key, key)
                    gps_info[sub_tag] = value[key]
        
        if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
            lat = get_decimal_from_dms(gps_info['GPSLatitude'], gps_info['GPSLatitudeRef'])
            lon = get_decimal_from_dms(gps_info['GPSLongitude'], gps_info['GPSLongitudeRef'])

            # Lấy địa chỉ từ Nominatim
            try:
                geolocator = Nominatim(user_agent="my_django_app")
                location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
                address = get_clean_address(location)
            except:
                address = ""

            return {
                "latitude": lat,
                "longitude": lon,
                "address": address
            }
            
    except Exception as e:
        print(f"Lỗi extract GPS: {e}")
    
    return None