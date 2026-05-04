import os
import streamlit as st

# ДИАГНОСТИКА: Проверка структуры проекта
st.sidebar.title("🔧 ДИАГНОСТИКА ПРОЕКТА")
st.sidebar.write("**Текущая рабочая директория:**", os.getcwd())
st.sidebar.write("**Содержимое текущей директории:**")

# Показываем все файлы и папки в текущей директории
for item in os.listdir():
    if os.path.isdir(item):
        st.sidebar.write(f"📁 {item}")
    else:
        st.sidebar.write(f"📄 {item}")

# Проверяем наличие папки pages
if "pages" in os.listdir() and os.path.isdir("pages"):
    st.sidebar.success("✅ Папка pages найдена!")

    # Проверяем содержимое папки pages
    st.sidebar.write("**Содержимое папки pages:**")
    for page_file in os.listdir("pages"):
        st.sidebar.write(f"- {page_file}")
else:
    st.sidebar.error("❌ Папка pages НЕ НАЙДЕНА в текущей директории!")

# Проверяем версию Streamlit
import streamlit

st.sidebar.write("**Версия Streamlit:**", streamlit.__version__)

# Проверяем, есть ли в сессии page (должно быть удалено!)
if 'page' in st.session_state:
    st.sidebar.warning("⚠️ ВНИМАНИЕ: st.session_state.page все еще существует!")