"""
Сервис для обработки PDF файлов и извлечения структурированных знаний с помощью AI
"""
from typing import List, Dict, Optional
import io
import json
import re

# Импорты PDF библиотек с обработкой ошибок
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

PDF_LIBS_AVAILABLE = PDFPLUMBER_AVAILABLE or PYPDF2_AVAILABLE

from app.services.llm_service import llm_service


class PDFProcessor:
    """Обработчик PDF файлов для извлечения знаний о бренде"""
    
    def __init__(self):
        self.llm = llm_service
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """
        Извлечение текста из PDF файла
        
        Args:
            pdf_bytes: Байты PDF файла
            
        Returns:
            Извлеченный текст
        """
        if not PDF_LIBS_AVAILABLE:
            raise ValueError(
                "PDF обработка недоступна: не установлены библиотеки. "
                "Установите: pip install pdfplumber PyPDF2"
            )

        text_parts: List[str] = []
        
        # Пробуем использовать pdfplumber (лучше для структурированных PDF)
        if PDFPLUMBER_AVAILABLE:
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                if text_parts:
                    full_text = "\n\n".join(text_parts)
                    return full_text.strip()
            except Exception as e:
                print(f"Ошибка при использовании pdfplumber: {e}")
        
        # Fallback на PyPDF2
        if PYPDF2_AVAILABLE:
            try:
                pdf_file = io.BytesIO(pdf_bytes)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            except Exception as e2:
                raise ValueError(f"Не удалось извлечь текст из PDF: {e2}")
        else:
            raise ValueError("Не установлены библиотеки для работы с PDF")
        
        if not text_parts:
            raise ValueError("Не удалось извлечь текст из PDF файла")
        
        full_text = "\n\n".join(text_parts)
        return full_text.strip()
    
    async def extract_knowledge_from_text(
        self,
        text: str,
        filename: Optional[str] = None,
        chunk_size: int = 3000
    ) -> List[Dict]:
        """
        Извлечение структурированных знаний из текста с помощью AI
        
        Args:
            text: Текст для обработки
            filename: Имя файла (для метаданных)
            chunk_size: Размер чанка текста для обработки (в символах)
            
        Returns:
            Список словарей с извлеченными знаниями
        """
        # Разбиваем текст на чанки для обработки
        chunks = self._split_text_into_chunks(text, chunk_size)
        
        all_knowledge = []
        
        for idx, chunk in enumerate(chunks):
            try:
                knowledge_items = await self._extract_knowledge_from_chunk(
                    chunk,
                    chunk_index=idx,
                    total_chunks=len(chunks),
                    filename=filename
                )
                all_knowledge.extend(knowledge_items)
            except Exception as e:
                print(f"Ошибка при обработке чанка {idx + 1}/{len(chunks)}: {e}")
                # Продолжаем обработку других чанков
                continue
        
        return all_knowledge
    
    def _split_text_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Разбивка текста на чанки"""
        chunks = []
        current_chunk = ""
        
        # Разбиваем по параграфам
        paragraphs = text.split("\n\n")
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Если параграф помещается в текущий чанк
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # Сохраняем текущий чанк и начинаем новый
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para
        
        # Добавляем последний чанк
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    async def _extract_knowledge_from_chunk(
        self,
        chunk_text: str,
        chunk_index: int = 0,
        total_chunks: int = 1,
        filename: Optional[str] = None
    ) -> List[Dict]:
        """Извлечение знаний из одного чанка текста с помощью AI"""
        
        system_prompt = """Ты помощник для извлечения структурированных знаний о бренде из текста.
Твоя задача - проанализировать предоставленный текст и извлечь ключевые знания о бренде, его философии, ценностях, продуктах, услугах и других важных аспектах.

Для каждого найденного знания создай объект со следующими полями:
- text: текст знания (краткий и информативный, 1-3 предложения)
- category: категория знания (brand_philosophy, materials, craftsmanship, style, service, collections, values, target_audience, use_cases, styling, custom_orders, или другая подходящая)
- source: источник (если указан в тексте, иначе null)

Верни массив объектов в формате JSON."""
        
        prompt = f"""Проанализируй следующий текст и извлеки структурированные знания о бренде:

{chunk_text}

Извлеки все важные знания о бренде, его философии, продуктах, услугах, ценностях и других аспектах.
Верни ТОЛЬКО валидный JSON массив объектов без дополнительного текста. Каждый объект должен содержать поля: text, category, source.

Пример формата:
[
  {{"text": "Текст знания", "category": "brand_philosophy", "source": "название_источника"}},
  {{"text": "Другое знание", "category": "materials", "source": null}}
]"""
        
        try:
            # Генерируем ответ через LLM
            response_text = await self.llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,  # Низкая температура для более точного извлечения
                max_tokens=2000
            )
            
            # Парсим JSON из ответа
            try:
                # Удаляем markdown код блоки если есть
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]
                
                response_text = response_text.strip()
                response = json.loads(response_text)
            except json.JSONDecodeError:
                # Если не удалось распарсить, пробуем найти JSON массив в тексте
                json_match = re.search(r'\[.*\{.*\}.*\]', response_text, re.DOTALL)
                if json_match:
                    try:
                        response = json.loads(json_match.group())
                    except:
                        # Пробуем найти объект с полем items
                        obj_match = re.search(r'\{.*"items".*:.*\[.*\{.*\}.*\].*\}', response_text, re.DOTALL)
                        if obj_match:
                            try:
                                response = json.loads(obj_match.group())
                            except:
                                response = {}
                        else:
                            response = {}
                else:
                    response = {}
            
            # Извлекаем items из ответа
            if isinstance(response, dict):
                items = response.get("items", [])
                if not items and isinstance(response, list):
                    items = response
            elif isinstance(response, list):
                items = response
            else:
                items = []
            
            # Добавляем метаданные о файле
            knowledge_items = []
            for item in items:
                if isinstance(item, dict) and item.get("text"):
                    knowledge_item = {
                        "text": item.get("text", ""),
                        "category": item.get("category"),
                        "source": item.get("source") or filename,
                        "metadata": {
                            "chunk_index": chunk_index,
                            "total_chunks": total_chunks,
                            "filename": filename
                        }
                    }
                    knowledge_items.append(knowledge_item)
            
            return knowledge_items
            
        except Exception as e:
            print(f"Ошибка при извлечении знаний через AI: {e}")
            # Fallback: создаем одно знание из всего чанка
            return [{
                "text": chunk_text[:500] + ("..." if len(chunk_text) > 500 else ""),
                "category": None,
                "source": filename,
                "metadata": {
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "filename": filename,
                    "extraction_method": "fallback"
                }
            }]
    
    async def process_pdf(
        self,
        pdf_bytes: bytes,
        filename: Optional[str] = None
    ) -> List[Dict]:
        """
        Полная обработка PDF файла: извлечение текста и структурирование знаний
        
        Args:
            pdf_bytes: Байты PDF файла
            filename: Имя файла
            
        Returns:
            Список словарей с извлеченными знаниями
        """
        # Извлекаем текст из PDF
        text = self.extract_text_from_pdf(pdf_bytes)
        
        if not text or len(text.strip()) < 50:
            raise ValueError("Не удалось извлечь достаточное количество текста из PDF")
        
        # Извлекаем структурированные знания с помощью AI
        knowledge_items = await self.extract_knowledge_from_text(text, filename)
        
        return knowledge_items


# Singleton instance
pdf_processor = PDFProcessor()
