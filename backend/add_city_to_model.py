"""
Добавляет поле city в модель User
"""

# Читаем файл
with open('app/models/user.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим строку с full_name и добавляем после нее city
new_lines = []
for line in lines:
    new_lines.append(line)
    if 'full_name = Column(String(255), nullable=True)  # полное имя покупателя' in line:
        new_lines.append('    city = Column(String(100), nullable=True)  # город покупателя\n')

# Записываем обратно
with open('app/models/user.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Поле city добавлено в модель User!")
