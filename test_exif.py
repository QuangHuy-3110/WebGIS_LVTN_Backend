import time
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
def _dms_to_decimal(dms, ref):
    degrees = float(dms[0])
    minutes = float(dms[1])
    seconds = float(dms[2])
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if ref in ['S', 'W']:
        decimal = -decimal
    return decimal

def test_exif_speed(image_path, iterations=50):
    print(f"\n--- [TEST EXIF METADATA] Lặp {iterations} lần loop ---")
    times = []
    
    for _ in range(iterations):
        t0 = time.time()
        
        img = Image.open(image_path)
        exif_data = img._getexif()
        
        gps_ifd = None
        for tag_id, value in exif_data.items():
            if TAGS.get(tag_id, tag_id) == 'GPSInfo':
                gps_ifd = value; break
                
        gps_info = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
        lat = _dms_to_decimal(gps_info['GPSLatitude'], gps_info['GPSLatitudeRef'])
        lng = _dms_to_decimal(gps_info['GPSLongitude'], gps_info['GPSLongitudeRef'])
        
        t1 = time.time()
        times.append((t1 - t0) * 1000)

    print(f"-> Tốc độ cắn toạ độ từ Ảnh cực ngắn: {sum(times)/iterations:.2f} ms (Yêu cầu: < 50ms)")
    print(f"-> Tọa độ test: Lat={lat:.5f}, Lng={lng:.5f}")

# Cung cấp đường dẫn ảnh (nhớ sửa file.jpg thành file của bạn)
test_exif_speed('/home/quanghuy/DaiHoc/LuanVanTotNghiep/Web_GIS/data/20260102_154430.jpg') 
