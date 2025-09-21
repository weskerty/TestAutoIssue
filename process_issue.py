import os
import re
import json
import base64
import subprocess
from pathlib import Path
from io import BytesIO
import requests
from bs4 import BeautifulSoup
from PIL import Image

class IssueProcessor:
    def __init__(self):
        self.issue_number = os.environ['ISSUE_NUMBER']
        self.issue_title = os.environ['ISSUE_TITLE']
        self.issue_body = os.environ['ISSUE_BODY']
        self.issue_user = os.environ['ISSUE_USER']
        self.target_dir = Path(os.environ['GITHUB_WORKSPACE']) / 'web' / 'Dinamico' / 'Corrupcion'
        self.groq_api_key = os.environ['GROQ_API_KEY']
        self.github_token = os.environ['GITHUB_TOKEN']
        self.image_buffer = None
        
        self.config = {
            'base_commit_message': 'Nueva Entrada:',
            'bot_signature': 'IssueBot',
            'max_filename_length': 100,
            'image_prompt': """Analiza esta imagen y responde ÚNICAMENTE con "APTA" o "NO_APTA".
            
            Una imagen es APTA si:
            - Es apropiada para todo público
            - No contiene contenido sexual, pornográfico o desnudos
            - No contiene violencia extrema o gore
            - Es relevante para contenido informativo/periodístico
            
            Una imagen es NO_APTA si:
            - Contiene desnudos o contenido sexual
            - Muestra violencia extrema o sangre excesiva
            - Es claramente inapropiada para menores
            
            Responde solo: APTA o NO_APTA""",
            'text_prompt': """Analiza el siguiente texto y fuentes, y responde ÚNICAMENTE con "VALIDO" o "INVALIDO".
            
            El texto es VÁLIDO si:
            - Tiene coherencia y estructura lógica
            - Presenta información detallada y específica
            - Las fuentes son enlaces válidos y relevantes
            - No es claramente spam, troll, discurso de odio o sin sentido
            - Tiene al menos 500 caracteres de contenido sustancial
            - Las fuentes proporcionan contexto o evidencia
            
            El texto es INVÁLIDO si:
            - Es muy corto o sin información útil
            - Es claramente spam, troll, discurso de odio o sin sentido
            - Las fuentes no son relevantes o son falsas
            - Contiene solo texto sin sentido
            - No aporta información valiosa
            - Contiene Scripts Sospechosos no relacionado a reproduccion multimedia
            
            Responde solo: VALIDO o INVALIDO"""
        }

    def make_groq_request(self, prompt, image_buffer=None):
        messages = []
        
        if image_buffer:
            image_data_url = f"data:image/jpeg;base64,{base64.b64encode(image_buffer).decode()}"
            messages.append({
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': image_data_url}}
                ]
            })
            model = 'meta-llama/llama-4-maverick-17b-128e-instruct'
        else:
            messages.append({'role': 'user', 'content': prompt})
            model = 'llama-3.3-70b-versatile'

        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {self.groq_api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'messages': messages,
                'model': model,
                'temperature': 0.1,
                'max_tokens': 100
            }
        )
        
        if not response.ok:
            raise Exception(f'Groq API Error: {response.status_code}')
        
        return response.json()['choices'][0]['message']['content'].strip()

    def parse_issue_body_html(self, body):
        soup = BeautifulSoup(body, 'html.parser')
        sections = {'title': '', 'description': '', 'fuentes': []}
        
        for heading in soup.find_all('h3'):
            heading_text = heading.get_text().strip()
            content_element = heading.find_next_sibling('p')
            
            if content_element:
                content = content_element.get_text().strip()
                
                if 'Título' in heading_text:
                    sections['title'] = content
                elif 'Descripción' in heading_text:
                    sections['description'] = content
                elif 'Fuentes' in heading_text:
                    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', content)
                    sections['fuentes'] = list(set(urls))
        
        if not sections['title'] or not sections['description'] or not sections['fuentes']:
            return self.parse_issue_body_fallback(body)
        
        return sections

    def parse_issue_body_fallback(self, body):
        sections = {'title': '', 'description': '', 'fuentes': []}
        
        title_match = re.search(r'### 📌 Título\s*\n\n(.*?)(?=\n### |$)', body, re.DOTALL)
        if title_match:
            sections['title'] = title_match.group(1).strip()
        
        desc_match = re.search(r'### 📝 Descripción\s*\r?\n+([\s\S]*?)(?=\n### |$)', body)
        if desc_match:
            sections['description'] = desc_match.group(1).strip()
        
        fuentes_match = re.search(r'### 🔗 Fuentes\s*\n\n(.*?)(?=\n### |$)', body, re.DOTALL)
        if fuentes_match:
            fuentes_text = fuentes_match.group(1).strip()
            urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', fuentes_text)
            lines = fuentes_text.split('\n')
            line_urls = []
            
            for line in lines:
                line = line.strip()
                if line.startswith('-') or line.startswith('*'):
                    url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', line)
                    if url_match:
                        line_urls.append(url_match.group())
            
            all_urls = list(set(urls + line_urls))
            sections['fuentes'] = all_urls
        
        return sections

    def extract_first_image(self, body):
        markdown_match = re.search(r'!\[.*?\]\((https?://[^\)]+)\)', body)
        if markdown_match:
            return markdown_match.group(1)
        
        html_match = re.search(r'<img[^>]+src=["\'](.*?)["\'][^>]*>', body)
        if html_match:
            return html_match.group(1)
        
        github_assets_match = re.search(r'https://github\.com/user-attachments/assets/[a-f0-9\-]+', body)
        if github_assets_match:
            return github_assets_match.group()
        
        return None

    def sanitize_filename(self, filename):
        sanitized = re.sub(r'[<>:"/\\|?*#@!$%^&()+={}[\]~`]', '', filename)
        sanitized = re.sub(r'[\s\-]+', '_', sanitized)
        sanitized = re.sub(r'\.{2,}', '.', sanitized)
        sanitized = re.sub(r'^\.+|\.+$', '', sanitized)
        sanitized = re.sub(r'[^\w._]', '', sanitized)
        sanitized = sanitized.lower()
        sanitized = re.sub(r'_{2,}', '_', sanitized)
        sanitized = re.sub(r'^_+|_+$', '', sanitized)
        
        if not sanitized:
            sanitized = 'entrada_sin_nombre'
        
        if len(sanitized) > self.config['max_filename_length']:
            sanitized = sanitized[:self.config['max_filename_length']]
            sanitized = re.sub(r'_+$', '', sanitized)
        
        if re.match(r'^\d', sanitized):
            sanitized = 'entrada_' + sanitized
        
        return sanitized

    def find_available_filename(self, base_filename, username):
        base_path = self.target_dir / f'{base_filename}.md'
        
        if not base_path.exists():
            return {'filename': base_filename, 'is_new': True}
        
        try:
            existing_content = base_path.read_text(encoding='utf-8')
            existing_user = self.extract_user_from_file(existing_content)
            
            if username and existing_user == username:
                return {'filename': base_filename, 'can_replace': True}
            
            counter = 1
            while True:
                new_filename = f'{base_filename}_{counter}'
                new_path = self.target_dir / f'{new_filename}.md'
                if not new_path.exists():
                    return {'filename': new_filename, 'is_new': True}
                counter += 1
        
        except Exception as e:
            print(f'Error leyendo archivo existente: {e}')
            counter = 1
            while True:
                new_filename = f'{base_filename}_{counter}'
                new_path = self.target_dir / f'{new_filename}.md'
                if not new_path.exists():
                    return {'filename': new_filename, 'is_new': True}
                counter += 1

    def extract_user_from_file(self, content):
        match = re.search(r'<!-- participant: (\w+) -->', content)
        return match.group(1) if match else None

    def download_and_process_image(self, image_url):
        print(f'📥 Descargando imagen desde: {image_url}')
        
        headers = {}
        if 'github.com/user-attachments/assets' in image_url:
            headers['Authorization'] = f'token {self.github_token}'
            headers['Accept'] = 'application/vnd.github.v3.raw'
        
        response = requests.get(image_url, headers=headers)
        
        if not response.ok:
            raise Exception(f'Error descargando imagen: {response.status_code}')
        
        print(f'📦 Imagen descargada, tamaño: {len(response.content)} bytes')
        
        try:
            image = Image.open(BytesIO(response.content))
            
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            
            output_buffer = BytesIO()
            image.save(output_buffer, format='JPEG', quality=90, optimize=True)
            cleaned_buffer = output_buffer.getvalue()
            
            print('🧹 Metadatos removidos de la imagen')
            self.image_buffer = cleaned_buffer
            return cleaned_buffer
        
        except Exception as e:
            print(f'⚠️ No se pudo limpiar metadatos: {e}, usando imagen original')
            self.image_buffer = response.content
            return response.content

    def save_processed_image(self, filename):
        if not self.image_buffer:
            raise Exception('No hay imagen procesada para guardar')
        
        image_path = self.target_dir / f'{filename}.jpg'
        image_path.write_bytes(self.image_buffer)
        print(f'💾 Imagen guardada en: {image_path}')
        return image_path

    def validate_content(self, description, fuentes, image_buffer):
        print('🔍 Validando contenido con IA...')
        
        if image_buffer:
            print('📸 Validando imagen...')
            
            try:
                image_result = self.make_groq_request(self.config['image_prompt'], image_buffer)
                print(f'Resultado imagen: {image_result}')
                
                if 'NO_APTA' in image_result:
                    raise Exception('La imagen no es apropiada para todo público. Sigue las Reglas.')
            
            except Exception as e:
                if 'Sigue las Reglas' in str(e):
                    raise e
                print(f'⚠️ No se pudo validar la imagen: {e}')
        
        print('📝 Validando texto y fuentes...')
        text_to_validate = f"""
        DESCRIPCIÓN:
        {description}
        
        FUENTES:
        {chr(10).join(fuentes)}
        """
        
        text_result = self.make_groq_request(self.config['text_prompt'] + '\n\nTEXTO A ANALIZAR:\n' + text_to_validate)
        print(f'Resultado texto: {text_result}')
        
        if 'INVALIDO' in text_result:
            raise Exception('El contenido del texto o las fuentes no son válidos. Sigue las Reglas.')
        
        print('✅ Validación exitosa')
        return True

    def create_markdown_file(self, filename, title, description, fuentes, username):
        content = ''
        if username:
            content += f'<!-- participant: {username} -->\n\n'
        
        content += f'# {title}\n\n'
        content += f'{description}\n\n'
        
        if fuentes:
            content += '## Fuentes\n\n'
            for fuente in fuentes:
                content += f'- {fuente}\n'
        
        file_path = self.target_dir / f'{filename}.md'
        file_path.write_text(content, encoding='utf-8')
        return file_path

    def add_comment(self, message, is_error=False):
        comment_body = f'❌ **Error**: {message}' if is_error else f'✅ **Éxito**: {message}'
        
        requests.post(
            f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}/issues/{self.issue_number}/comments',
            headers={
                'Authorization': f'token {self.github_token}',
                'Content-Type': 'application/json'
            },
            json={'body': comment_body}
        )

    def close_issue(self):
        requests.patch(
            f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}/issues/{self.issue_number}',
            headers={
                'Authorization': f'token {self.github_token}',
                'Content-Type': 'application/json'
            },
            json={'state': 'closed'}
        )

    def run_git_command(self, command):
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.environ['GITHUB_WORKSPACE'])
        if result.returncode != 0:
            raise Exception(f'Git command failed: {result.stderr}')
        return result.stdout

    def process(self):
        try:
            print(f'🚀 Procesando issue #{self.issue_number} de {self.issue_user}')
            
            if not self.groq_api_key:
                raise Exception('GROQ_API_KEY no está configurado')
            
            sections = self.parse_issue_body_html(self.issue_body)
            first_image = self.extract_first_image(self.issue_body)
            
            print('📋 Contenido parseado:', {
                'issue_title': self.issue_title,
                'parsed_title': sections['title'],
                'description_length': len(sections['description']),
                'fuentes_count': len(sections['fuentes']),
                'fuentes': sections['fuentes'][:3],
                'first_image': first_image or 'ninguna'
            })
            
            final_title = sections['title'] or re.sub(r'^\[Info\]\s*', '', self.issue_title, flags=re.IGNORECASE).strip()
            
            if not final_title or len(final_title) < 3:
                raise Exception('El título es muy corto o está vacío')
            
            if not sections['description'] or len(sections['description']) < 500:
                raise Exception('La descripción debe tener al menos 500 caracteres')
            
            if len(sections['fuentes']) < 3:
                raise Exception('Debe proporcionar al menos 3 fuentes (URLs)')
            
            if not first_image:
                raise Exception('Debe incluir al menos una imagen')
            
            image_buffer = self.download_and_process_image(first_image)
            self.validate_content(sections['description'], sections['fuentes'], image_buffer)
            
            self.target_dir.mkdir(parents=True, exist_ok=True)
            
            sanitized_title = self.sanitize_filename(final_title)
            file_info = self.find_available_filename(sanitized_title, self.issue_user)
            final_filename = file_info['filename']
            
            self.save_processed_image(final_filename)
            
            print('📝 Creando archivo markdown...')
            self.create_markdown_file(
                final_filename,
                final_title,
                sections['description'],
                sections['fuentes'],
                self.issue_user
            )
            
            self.run_git_command('git config --global user.name "GitHub Action"')
            self.run_git_command('git config --global user.email "action@github.com"')
            
            print('📤 Realizando commit...')
            commit_message = f'{self.config["base_commit_message"]} {final_filename} {self.config["bot_signature"]}'
            self.run_git_command('git add .')
            self.run_git_command(f'git commit -m "{commit_message}"')
            self.run_git_command('git push')
            
            success_message = f'Entrada creada exitosamente: **{final_title}**\n\n'
            success_message += f'📁 Archivo: `{final_filename}.md`\n'
            success_message += f'👤 Usuario: {self.issue_user}\n'
            success_message += f'📊 Fuentes encontradas: {len(sections["fuentes"])}\n'
            
            if file_info.get('can_replace'):
                success_message += '🔄 Archivo reemplazado (mismo usuario)\n'
            elif final_filename != sanitized_title:
                success_message += '🔢 Nuevo archivo creado (conflicto de nombre)\n'
            
            self.add_comment(success_message)
            self.close_issue()
            
            print('✅ Issue procesado exitosamente')
        
        except Exception as error:
            print(f'❌ Error procesando issue: {error}')
            self.add_comment(str(error), True)

if __name__ == '__main__':
    processor = IssueProcessor()
    processor.process()
