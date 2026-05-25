# Domo - Context y Guía de Desarrollo

## 1. Resumen del Proyecto
* **¿Qué es?:** Domo es una herramienta web interna que cuenta con dos módulos principales: uno para la visualización de estadísticas de soporte y otro para la automatización de respuestas utilizando Inteligencia Artificial.
* **Objetivo Principal:** Automatizar respuestas de soporte técnico. El sistema recibe un ID de ticket principal y una causa. La IA debe buscar los últimos 10 tickets históricos en Zendesk que compartan esa misma causa, analizar cómo se resolvieron y, con base en ese contexto, generar una propuesta de respuesta óptima y consistente para el nuevo ticket.
* **Audiencia/Usuarios:** Equipo de soporte técnico de la plataforma SaaS.

## 2. Stack Tecnológico y Versiones
* [cite_start]**Base de Entorno:** Python 3.12 ejecutándose en un contenedor basado en `python:3.12-slim`[cite: 1].
* [cite_start]**Framework Backend:** FastAPI para la construcción de endpoints asíncronos[cite: 3].
* [cite_start]**Servidor de Aplicación:** Uvicorn configurado en el puerto 8000[cite: 2, 3].
* [cite_start]**Cliente HTTP:** HTTPX para realizar llamadas asíncronas de alto rendimiento a la API externa de Zendesk[cite: 3].
* **Frontend:** Arquitectura nativa y ligera compuesta por HTML5, CSS3 moderno (uso de Variables CSS) y Vanilla JavaScript (ES6+).
* **Gráficos:** Chart.js v4.4.0 integrado mediante CDN en el cliente.
* [cite_start]**Contenedorización:** Docker para el empaquetado del entorno completo[cite: 1, 2].

## 3. Comandos del Proyecto (Crucial para Claude Code)
* [cite_start]**Instalar dependencias locales:** `pip install -r requirements.txt` [cite: 3]
* **Iniciar servidor de desarrollo (con autoreload):** `uvicorn main:app --reload --port 8000`
* **Construir imagen Docker:** `docker build -t domo-support .`
* **Ejecutar contenedor Docker:** `docker run -p 8000:8000 domo-support`

## 4. Arquitectura y Estructura de Carpetas
El proyecto organiza el backend en la raíz y el frontend dentro del directorio de estáticos que sirve FastAPI:
* `/main.py`: Punto de entrada de la aplicación. Contiene la inicialización de FastAPI, la lógica de negocio de extracción de métricas de Zendesk y el montaje de los archivos estáticos.
* [cite_start]`/requirements.txt`: Definición de dependencias de Python (fastapi, uvicorn, httpx, python-multipart)[cite: 3].
* [cite_start]`/Dockerfile`: Instrucciones de construcción automatizada de la imagen de Docker[cite: 1, 2].
* `/static/`: Directorio raíz para los recursos del frontend atendidos por el servidor.
  * `/static/index.html`: Estructura del Dashboard y divisiones de las pestañas de Métricas e IA.
  * `/static/css/style.css`: Hoja de estilos global, paleta de colores oscura y diseño de interfaces.
  * `/static/js/script.js`: Manejo del DOM del cliente, peticiones fetch hacia `/api/` y renderizado de componentes.

## 5. Guía de Estilo y Reglas Estrictas
* **Restricción Absoluta de Módulos:** EL MÓDULO DE ESTADÍSTICAS ESTÁ COMPLETADO Y ESTABLE. Queda estrictamente prohibido modificar o alterar los endpoints `/api/resolution-metrics`, `/api/causa-metrics` o las funciones de JS y CSS que le dan vida. El enfoque exclusivo debe ser el desarrollo del módulo de Inteligencia Artificial.
* **Idiomas de Desarrollo:** Todo el código del backend (nombres de funciones, variables, rutas de endpoints) y los comentarios técnicos deben escribirse estrictamente en **Inglés**. La interfaz de usuario (HTML) y los mensajes de cara al usuario se mantienen en **Español**.
* **Frontend Nativo:** Está prohibido instalar o intentar compilar frameworks modernos como React, Vue o utilidades como Tailwind. Toda nueva interactividad debe resolverse extendiendo `/static/js/script.js` con JavaScript nativo y el diseño visual mediante `/static/css/style.css`.
* **Manejo de Errores en Backend:** Todos los nuevos endpoints deben envolverse en bloques `try/except` y, en caso de fallo, retornar una respuesta JSON con la estructura estándar del proyecto: `{ "success": false, "error": "Mensaje de error descriptivo" }`.

## 6. Estado Actual y Próximos Pasos
* **Estado:** Los endpoints de análisis de causas y tiempos de resolución están operativos. El frontend cuenta ya con la maquetación visual y selectores para la pestaña de Inteligencia Artificial.
* **Próxima Tarea:** Desarrollar el endpoint correspondiente en `main.py` para invocar la API de Gemini. La función debe recibir el ID del ticket actual y su causa, orquestar la obtención de los últimos 10 tickets resueltos con esa misma causa desde la API de Zendesk, estructurar el Prompt del sistema y retornar la respuesta generada para que sea pintada en la interfaz del cliente.

## 7. Directiva de Prompt para la IA (System Prompt de Gemini)
Cuando estructures la llamada hacia la API de Gemini, debes inyectar la siguiente instrucción de sistema:
> "Eres un agente de soporte técnico de un servicio SaaS. Te vamos a proporcionar los últimos 10 tickets históricos asociados a una causa específica para que analices el contexto del caso y su respectiva solución. También recibirás un nuevo ticket entrante. Tu objetivo es generar una respuesta profesional y precisa para este nuevo ticket, tomando como referencia y manteniendo la consistencia con las soluciones dadas en los casos anteriores."

## 8. Credenciales y Variables de Entorno
*Las claves secretas NO deben guardarse en el código ni en este archivo markdown. Claude debe configurarlas en un archivo `.env` local y leerlas a través de `os.getenv()`:*
* `ZD_SUBDOMAIN`: Subdominio de Zendesk (ej: `domustech`).
* `ZD_EMAIL`: Correo electrónico de acceso a Zendesk.
* `ZD_API_TOKEN`: Token de autenticación de la API de Zendesk.
* `GEMINI_API_KEY`: Clave de acceso para la API de Google Gemini.

## 9. Documentación de Referencia
* **Zendesk API Core Reference:** https://developer.zendesk.com/api-reference/