import csv
import sqlite3
import streamlit as st
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool

# Inisialisasi DB SQLite dan Import dari CSV
def init_db_from_csv(csv_file='src\\hok_meta_heroes.csv'):
    conn = sqlite3.connect('db\\hok_meta.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS heroes
                 (name TEXT, primary_lane TEXT, tier TEXT, win_rate REAL, pick_rate REAL, ban_rate REAL, description TEXT)''')

    # Baca CSV
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip header jika ada
        heroes_data = []
        for row in reader:
            if len(row) >= 7:  # Validasi kolom
                name = row[0].strip()
                primary_lane = row[1].strip()
                tier = row[2].strip()
                try:
                    win_rate = float(row[3]) if row[3] else 0.0
                    pick_rate = float(row[4]) if row[4] else 0.0
                    ban_rate = float(row[5]) if row[5] else 0.0
                except ValueError:
                    win_rate = pick_rate = ban_rate = 0.0
                description = row[6].strip() if len(row) > 6 else ""
                heroes_data.append((name, primary_lane, tier, win_rate, pick_rate, ban_rate, description))
    
    # Insert data
    if heroes_data:
        c.executemany('INSERT INTO heroes VALUES (?, ?, ?, ?, ?, ?, ?)', heroes_data)
    conn.commit()
    conn.close()

# Jalankan init (hanya sekali, atau comment jika sudah ada DB)
init_db_from_csv()

# Tool untuk Function Calling (Query DB dengan Sort & Prioritas S-Tier, Output Teks)
@tool
def get_meta_heroes_by_lane(lane: str):
    """Mengembalikan daftar hero meta untuk lane tertentu dalam teks, diurutkan berdasarkan win_rate tertinggi. Prioritaskan S-tier sebagai OP."""
    conn = sqlite3.connect('db\\hok_meta.db')
    c = conn.cursor()
    # Query dengan sort by win_rate DESC
    c.execute("""
        SELECT name, primary_lane, tier, win_rate, pick_rate, ban_rate, description 
        FROM heroes 
        WHERE primary_lane = ? 
        ORDER BY win_rate DESC
    """, (lane,))
    results = c.fetchall()
    conn.close()
    
    if not results:
        return f"Tidak ada data untuk lane '{lane}'. Lane valid: Clash Lane, Mid Lane, Farm Lane, Jungle, Roaming."
    
    # Format sebagai teks langsung
    response_text = f"Untuk {lane}, hero yang lagi OP banget dan bagus utama itu ada dua:\n"
    s_tier = [r for r in results if r[2] == 'S']
    a_tier = [r for r in results if r[2] == 'A']

    if s_tier:
        for i, hero in enumerate(s_tier, 1):
            name, _, tier, win_rate, pick_rate, ban_rate, desc = hero
            response_text += f"{i}. ***{name}***: Ini hero paling top di {lane} sekarang! Win rate-nya tinggi banget, di {win_rate}%, dan ban rate-nya juga di {ban_rate}%. {desc} Cocok buat kamu yang suka main agresif dan tahan banting.\n"
    
    if a_tier:
        response_text += "Sebagai alternatif conditional kalau S-tier di-ban, kamu bisa banget coba hero-hero A-tier ini:\n"
        for i, hero in enumerate(a_tier, 1):
            name, _, tier, win_rate, pick_rate, ban_rate, desc = hero
            response_text += f"{i}. ***{name}***: Ini mungking jadi solusi untuk dipakai, win rate-nya {win_rate}%. Kalau tim butuh pakai aja.\n"         
    return response_text

# Inisialisasi Model dengan Parameter
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key='YOUR_GOOGLE_API_KEY',
    temperature=0.7,
    max_output_tokens=1500,
    top_p=0.95,
    top_k=40
)
tools = [get_meta_heroes_by_lane]
agent = create_react_agent(llm, tools)

# System Prompt untuk Chatbot
system_prompt = SystemMessage(content="""
Kamu adalah assistant gamer professional dengan analisis yang baik dan paham semua hero dari nama hero, jumlah semua hero (berdasarkan dataset), skill, hingga kelebihan dan kekurangan khusus pada game Honor of Kings (HoK), MOBA mobile dengan hero unik dan meta berubah per patch. 
Pahami nama-nama hero Hok pada database dan statistiknya (win rate, pick rate, ban rate, deskripsi singkat).
-jika user tanya nama hero HoK misal (apakah ada hero bernama dyadia?), maka jawab berdasarkan name serta data pada dataset
Fokus bantu user dalam role hero seperti support, tank, mage, assassin, marksman, fighter.
fokus bantu user dalam memilih hero yang cocok pada lane tertentu: Clash Lane, Mid Lane, Farm Lane, Jungle, Roaming.
Gunakan tool get_meta_heroes_by_lane untuk ambil data akurat dari DB (diurutkan win_rate tertinggi).
Aturan respons:
- Sebut A-tier sebagai 'alternatif conditional' (misal: bagus kalau musuh X, atau jika S-tier diban).
- Prioritaskan rekomendasi berdasarkan win_rate (contoh: 'Loong OP karena win_rate 55.3%').
- Jelaskan alasan: win_rate, pick/ban rate, deskripsi playstyle.
- Jika query umum ('hero OP di HoK'), tanya lane dulu atau beri overview S-tier top.
- Jangan hallucinate; selalu pakai data tool jika relevan.
""")

# Streamlit UI
st.image("src\\Honor-of-Kings-Banner.jpg", use_container_width=True)
st.title("Chatbot Meta Hero Honor of Kings")
st.write("Tanya meta hero Honor of Kings per lane. Contoh: 'Hero OP di Farm Lane?' atau 'Rekomendasi Jungle kalau musuh banyak assassin?'")
st.caption("Dataset dari meta Oktober 2025, prioritaskan S-tier berdasarkan win rate.")

# Memory: Simpan history di session state dengan batasan
if "messages" not in st.session_state:
    st.session_state.messages = [system_prompt]
MAX_MESSAGES = 10  # Untuk hindari overload

# Tampilkan chat history
for message in st.session_state.messages[1:]:  # Skip system prompt
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.write(message.content)
    elif isinstance(message, AIMessage):
        with st.chat_message("assistant"):
            st.write(message.content)

# Input user
if user_input := st.chat_input("Tulis pertanyaanmu tentang Hero HoK yang sedang meta..."):
    st.session_state.messages.append(HumanMessage(content=user_input))
    with st.chat_message("user"):
        st.write(user_input)
    
    # Potong history jika terlalu panjang
    if len(st.session_state.messages) > MAX_MESSAGES:
        st.session_state.messages = [system_prompt] + st.session_state.messages[-MAX_MESSAGES + 1:]
    
    # Jalankan agent
    with st.spinner("Bot berfikir..."):
        try:
            response = agent.invoke({"messages": st.session_state.messages})
            # Debug: Cek isi response
            print("Raw response:", response)
            print("AI response content (raw):", response['messages'][-1].content if response['messages'] else "No content")
        except Exception as e:
            print(f"Error during agent invoke: {e}")
            response = {"messages": [AIMessage(content="Maaf, ada error saat proses. Coba lagi ya!")]}

    # Ambil dan bersihkan respons
    ai_response = response['messages'][-1].content if response['messages'] and len(response['messages']) > 0 else None
    print("AI response content (before filter):", ai_response)  # Debug sebelum filter
    
    if ai_response:
        # Cek tipe dan ekstrak teks dari dictionary
        if isinstance(ai_response, dict):
            ai_response = ai_response.get('text', '')  # Ambil nilai 'text' dari dict
            print("AI response content (after dict extract):", ai_response)
        elif isinstance(ai_response, list):
            ai_response = ' '.join(str(item.get('text', '')) for item in ai_response if isinstance(item, dict))  # Gabung list dict
            print("AI response content (after list join):", ai_response)
        # Sederhanakan pemfilteran, hapus cek simbol berlebih
        ai_response = re.sub(r'\["type":\s*"text",\s*"text":\s*"(.+?)"\]', r'\1', ai_response).strip()  # Hapus JSON wrapper
        if not ai_response:
            ai_response = "Coba tanya lane spesifik ya, Contoh: 'Hero OP di Jungle?'"
    else:
        ai_response = "Coba tanya lane spesifik ya, Contoh: 'Hero OP di Jungle?'"

    st.session_state.messages.append(AIMessage(content=ai_response))
    with st.chat_message("assistant"):
        st.write(ai_response)