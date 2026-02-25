"""
Тест извлечения base_url из xml_url
"""

xml_url = "https://s22b2e4d6.fastvps-server.com/1c_exchange/uploaded/import.xml"

# Текущий метод
base_url = xml_url.rsplit('/', 1)[0] if '/' in xml_url else None

print("=" * 80)
print("ТЕСТ ИЗВЛЕЧЕНИЯ BASE_URL")
print("=" * 80)
print()
print(f"XML URL: {xml_url}")
print(f"Base URL (текущий метод): {base_url}")
print()

# Проверяем, что из него получается для относительных путей
from urllib.parse import urljoin

test_images = [
    "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_277b494ad0ed11f08e4dfa163e4cc04e.jpeg",
    "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_27b1896ad0ed11f08e4dfa163e4cc04e.jpeg"
]

print("Преобразование относительных путей:")
for img in test_images:
    full_url = urljoin(base_url + '/', img.lstrip('/'))
    print(f"  {img}")
    print(f"    -> {full_url}")
    print()

print("=" * 80)
print("Ожидаемые URL:")
print("  https://s22b2e4d6.fastvps-server.com/1c_exchange/uploaded/import_files/ec/...")
print()
print("Фактические URL корректны!" if "uploaded/import_files" in urljoin(base_url + '/', test_images[0].lstrip('/')) else "Требуется корректировка!")
print("=" * 80)
