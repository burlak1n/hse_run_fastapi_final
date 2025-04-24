#!/usr/bin/env python3
import os
from PIL import Image, ImageDraw, ImageFont
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

class BadgeGenerator:
    def __init__(self, background_path="background.webp"):
        self.background_path = background_path
        self.image = None
        self.load_background()
        self.red_color = (200, 0, 2)  # C80002 в RGB
        self.dark_gray = (50, 50, 50)  # Темно-серый цвет
    
    def load_background(self):
        """Загружает фоновое изображение"""
        if os.path.exists(self.background_path):
            self.image = Image.open(self.background_path)
        else:
            # Создаем пустое изображение если фон не найден
            self.image = Image.new('RGBA', (800, 1120), (255, 255, 255, 255))
    
    def draw_multiline_text_centered(self, draw, text, font, color, y_position, width):
        """
        Рисует многострочный текст с центрированием каждой строки
        
        :param draw: объект ImageDraw
        :param text: текст для отображения (может содержать \n)
        :param font: шрифт для отображения
        :param color: цвет текста
        :param y_position: начальная позиция по Y
        :param width: ширина изображения для центрирования
        :return: высота всего текста
        """
        lines = text.split('\n')
        line_height = 0
        total_height = 0
        
        for line in lines:
            # Получаем размеры строки
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            
            # Центрируем строку
            x_position = (width - line_width) // 2
            
            # Рисуем строку
            draw.text((x_position, y_position + total_height), line, font=font, fill=color)
            
            # Увеличиваем общую высоту
            total_height += line_height + 5  # Добавляем небольшой промежуток между строками
        
        return total_height
    
    def add_badge_text(self, role, name, role_font_path="Involve-Regular.ttf", name_font_path="Involve-Medium.ttf"):
        """
        Добавляет текст должности и имени в стиле бейджа HSE RUN
        
        :param role: Должность (красным цветом)
        :param name: ФИО (темно-серым цветом)
        :param role_font_path: Путь к шрифту Involve Regular для должности
        :param name_font_path: Путь к шрифту Involve Medium для имени
        """
        if self.image is None:
            self.load_background()
            
        draw = ImageDraw.Draw(self.image)
        width, height = self.image.size
        
        # Размеры шрифтов
        role_font_size = 96
        name_font_size = 115
        
        # Загружаем шрифты для должности и имени
        try:
            # Шрифт для должности
            if os.path.exists(role_font_path):
                role_font = ImageFont.truetype(role_font_path, role_font_size)
            else:
                role_font = ImageFont.load_default()
                print(f"Шрифт {role_font_path} не найден, используется стандартный")
            
            # Шрифт для имени
            if os.path.exists(name_font_path):
                name_font = ImageFont.truetype(name_font_path, name_font_size)
            else:
                name_font = ImageFont.load_default()
                print(f"Шрифт {name_font_path} не найден, используется стандартный")
        except Exception as e:
            print(f"Ошибка загрузки шрифта: {e}")
            role_font = ImageFont.load_default()
            name_font = ImageFont.load_default()
        
        # Расстояние между ролью и именем
        spacing = 40
        
        # Примерная высота блоков текста (для предварительного расчёта)
        if '\n' in role:
            role_lines = role.count('\n') + 1
            role_test_height = role_font.getbbox("Тестовая строка")[3] * role_lines
        else:
            role_test_height = role_font.getbbox(role)[3]
            
        if '\n' in name:
            name_lines = name.count('\n') + 1
            name_test_height = name_font.getbbox("Тестовая строка")[3] * name_lines
        else:
            name_test_height = name_font.getbbox(name)[3]
            
        # Общая высота блока текста (примерная)
        total_text_height = role_test_height + spacing + name_test_height
        
        # Начальная Y-координата для блока текста
        start_y = (height - total_text_height) // 2
        
        # Рисуем должность (центрируем каждую строку)
        role_height = self.draw_multiline_text_centered(draw, role, role_font, self.red_color, start_y, width)
        
        # Рисуем имя (центрируем каждую строку)
        name_y = start_y + role_height + spacing
        self.draw_multiline_text_centered(draw, name, name_font, self.dark_gray, name_y, width)
        
        return self
    
    def add_text(self, text, position=(50, 50), font_size=30, color=(0, 0, 0), font_path=None):
        """Добавляет текст на изображение"""
        if self.image is None:
            self.load_background()
            
        draw = ImageDraw.Draw(self.image)
        
        # Используем системный шрифт если не указан путь к шрифту
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
        else:
            # Используем стандартный шрифт
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()
        
        draw.text(position, text, font=font, fill=color)
        return self
    
    def export_webp(self, output_path="img/badge.webp", quality=80):
        """Экспортирует изображение в формате WEBP"""
        if self.image is None:
            raise ValueError("Изображение не загружено")
            
        self.image.save(output_path, "WEBP", quality=quality)
        return output_path
    
    def export_png(self, output_path="img/badge.png"):
        """Экспортирует изображение в формате PNG"""
        if self.image is None:
            raise ValueError("Изображение не загружено")
            
        self.image.save(output_path, "PNG")
        return output_path
    
    def export_pdf(self, output_path="img/badge.pdf"):
        """Экспортирует изображение в формате PDF"""
        if self.image is None:
            raise ValueError("Изображение не загружено")
            
        # Получаем размеры изображения
        width, height = self.image.size
        
        # Создаем PDF с правильными размерами
        c = canvas.Canvas(output_path, pagesize=(width, height))
        
        # Сохраняем изображение во временный файл
        temp_img_path = "temp_badge_image.png"
        self.image.save(temp_img_path, "PNG")
        
        # Добавляем изображение в PDF
        c.drawImage(temp_img_path, 0, 0, width, height)
        c.save()
        
        # Удаляем временный файл
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)
            
        return output_path

# Пример использования
if __name__ == "__main__":
    badge = BadgeGenerator()
    badge.add_badge_text("дизайнер", "Аксён\nВасильев")
    # badge.export_webp()
    # badge.export_png()
    badge.export_pdf()
    print("Успешно создано!")
