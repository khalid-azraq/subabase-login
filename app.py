import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv

load_dotenv() # تحميل متغيرات البيئة من .env

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# قد لا تحتاج إلى تهيئة عميل Supabase هنا إذا كان JS سيتعامل مع كل شيء
# ولكن من الجيد تمرير الإعدادات إلى القوالب
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

@app.route('/')
def index():
    if 'user_session' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET'])
def login_page():
    if 'user_session' in session: # إذا كان المستخدم مسجلاً دخوله بالفعل، اذهب إلى الداشبورد
        return redirect(url_for('dashboard'))
    return render_template('login.html', supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)

@app.route('/dashboard')
def dashboard():
    if 'user_session' not in session:
        return redirect(url_for('login_page'))
    # يمكنك هنا جلب بيانات المستخدم من الجلسة أو إعادة التحقق من Supabase إذا لزم الأمر
    user_info = session.get('user_session')
    return render_template('dashboard.html', user_email=user_info.get('email', 'المستخدم'))




# هذا المسار مهم لإنشاء جلسة Flask بعد نجاح تسجيل الدخول من جانب العميل
@app.route('/set-session', methods=['POST'])
def set_session():
    data = request.get_json()
    access_token = data.get('access_token')
    user_data = data.get('user') # بيانات المستخدم من Supabase

    if not access_token or not user_data:
        return jsonify({'error': 'Missing token or user data'}), 400

    # هنا يمكنك التحقق من الـ access_token مع Supabase إذا أردت طبقة أمان إضافية
    # باستخدام مكتبة supabase-py:
    # from supabase import create_client, Client
    # supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # try:
    #     user_response = supabase_client.auth.get_user(access_token)
    #     # إذا لم يثر استثناء، فالتوكن صالح
    # except Exception as e:
    #     return jsonify({'error': 'Invalid token', 'details': str(e)}), 401
    
    session['user_session'] = {
        'access_token': access_token,
        'id': user_data.get('id'),
        'email': user_data.get('email'),
        'aud': user_data.get('aud')
        # يمكنك إضافة المزيد من بيانات المستخدم هنا
    }
    return jsonify({'message': 'Session created successfully'}), 200

@app.route('/signup', methods=['GET'])
def signup_page():
    if 'user_session' in session: # إذا كان المستخدم مسجلاً دخوله بالفعل، اذهب إلى الداشبورد
        return redirect(url_for('dashboard'))
    return render_template('signup.html', supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)

@app.route('/logout')
def logout():
    session.pop('user_session', None)
    # ملاحظة: تسجيل الخروج من Supabase يتم عبر JavaScript في العميل
    return redirect(url_for('login_page'))




if __name__ == '__main__':
    app.run(debug=True)