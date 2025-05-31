import os
import datetime # تأكد من استيراد datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash # أضفت flash
from dotenv import load_dotenv
from supabase import create_client, Client # لاستخدام Supabase من جانب الخادم
import paypalrestsdk

# تحميل متغيرات البيئة من .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY') # ضروري لـ session و flash messages

# --- تهيئة Supabase ---
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_KEY') # هذا مفتاح anon public للواجهة الأمامية
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY') # هذا مفتاح service_role السري للخادم

if not all([SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY]):
    raise ValueError("Supabase URL, Anon Key, or Service Key not found in environment variables.")

# عميل Supabase للعمليات من جانب الخادم (يتطلب مفتاح service_role)
supabase_service_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# --- تهيئة PayPal SDK ---
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")

if not all([PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET]):
    app.logger.warning("PayPal Client ID or Client Secret not found. PayPal integration might not work.")
else:
    try:
        paypalrestsdk.configure({
            "mode": PAYPAL_MODE,
            "client_id": PAYPAL_CLIENT_ID,
            "client_secret": PAYPAL_CLIENT_SECRET
        })
        app.logger.info(f"PayPal SDK configured for mode: {PAYPAL_MODE}")
    except Exception as e:
        app.logger.error(f"Error configuring PayPal SDK: {e}")


# ===== مسارات المصادقة الأساسية =====
@app.route('/')
def index():
    if 'user_session' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET'])
def login_page():
    if 'user_session' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', supabase_url=SUPABASE_URL, supabase_key=SUPABASE_ANON_KEY)

@app.route('/signup', methods=['GET'])
def signup_page():
    if 'user_session' in session:
        return redirect(url_for('dashboard'))
    return render_template('signup.html', supabase_url=SUPABASE_URL, supabase_key=SUPABASE_ANON_KEY)

@app.route('/dashboard')
def dashboard():
    if 'user_session' not in session:
        flash("الرجاء تسجيل الدخول للوصول إلى هذه الصفحة.", "warning")
        return redirect(url_for('login_page'))
    
    user_info = session.get('user_session')
    return render_template('dashboard.html', user_email=user_info.get('email', 'المستخدم'))

@app.route('/set-session', methods=['POST'])
def set_session():
    data = request.get_json()
    access_token = data.get('access_token')
    user_data = data.get('user')

    if not access_token or not user_data:
        return jsonify({'error': 'Missing token or user data'}), 400
    
    session['user_session'] = {
        'access_token': access_token,
        'id': user_data.get('id'),
        'email': user_data.get('email'),
        'aud': user_data.get('aud')
    }
    return jsonify({'message': 'Session created successfully'}), 200

@app.route('/logout')
def logout():
    session.pop('user_session', None)
    flash("تم تسجيل خروجك بنجاح.", "info")
    return redirect(url_for('login_page'))


# ===== مسارات الاشتراكات و PayPal =====

@app.route('/pricing')
def pricing_page():
    if 'user_session' not in session:
        flash("الرجاء تسجيل الدخول لعرض الباقات.", "warning")
        return redirect(url_for('login_page'))
    
    user_id = session['user_session']['id']
    current_plan = "free" # القيمة الافتراضية
    
    try:
        response = supabase_service_client.table('subscriptions')\
            .select('plan_name, status')\
            .eq('user_id', user_id)\
            .eq('status', 'active')\
            .maybe_single().execute() # maybe_single() أفضل إذا كان من المتوقع عدم وجود سجل أو سجل واحد فقط
        
        if response.data:
            current_plan = response.data['plan_name']
    except Exception as e:
        app.logger.error(f"Error fetching current plan for user {user_id}: {e}")
        flash("حدث خطأ أثناء جلب معلومات اشتراكك.", "danger")

    return render_template('pricing.html', 
                           PAYPAL_CLIENT_ID=PAYPAL_CLIENT_ID, 
                           current_plan=current_plan)


@app.route('/create-paypal-subscription', methods=['POST'])
def create_paypal_subscription():
    if 'user_session' not in session:
        return jsonify({'error': 'User not authenticated'}), 401

    try:
        data = request.get_json()
        # تأكد من أن هذه المعرفات هي معرفات خطط الفوترة (Billing Plan IDs) من PayPal
        paypal_billing_plan_id = data.get('plan_id') 
        plan_name_from_frontend = data.get('plan_name') # "pro" أو "premium"

        if not paypal_billing_plan_id or not plan_name_from_frontend:
            return jsonify({'error': 'Missing plan_id or plan_name'}), 400

        user_supabase_id = session['user_session']['id']
        
        start_time_paypal_format = (datetime.datetime.utcnow() + datetime.timedelta(seconds=60)).strftime('%Y-%m-%dT%H:%M:%SZ')

        billing_agreement_attributes = {
            "name": f"{plan_name_from_frontend.capitalize()} Plan for {user_supabase_id}",
            "description": f"Subscription to the {plan_name_from_frontend.capitalize()} Plan.",
            "start_date": start_time_paypal_format,
            "plan": {"id": paypal_billing_plan_id},
            "payer": {"payment_method": "paypal"},
            "override_merchant_preferences": {
                "return_url": url_for('payment_success_paypal', _external=True),
                "cancel_url": url_for('payment_cancel_paypal', _external=True)
            }
        }
        
        agreement = paypalrestsdk.BillingAgreement(billing_agreement_attributes)

        if agreement.create():
            approval_url = next((link.href for link in agreement.links if link.rel == "approval_url"), None)
            
            if approval_url:
                paypal_billing_agreement_id = agreement.id # هذا هو I-XXXXXXXXXXXX
                try:
                    # إنشاء/تحديث سجل أولي للاشتراك في Supabase
                    upsert_data = {
                        'user_id': user_supabase_id,
                        'paypal_subscription_id': paypal_billing_agreement_id,
                        'plan_name': plan_name_from_frontend,
                        'status': 'pending_paypal_approval',
                        # لا تضع تواريخ البدء/الانتهاء هنا، انتظر webhook التفعيل
                    }
                    # on_conflict='paypal_subscription_id' يفترض أن paypal_subscription_id عمود فريد
                    # إذا لم يكن كذلك، ستحتاج إلى منطق select ثم insert/update
                    supabase_service_client.table('subscriptions').upsert(upsert_data, on_conflict='paypal_subscription_id').execute()
                    app.logger.info(f"Upserted pending subscription for agreement: {paypal_billing_agreement_id}")
                except Exception as db_error:
                    app.logger.error(f"DB error creating/updating pending subscription: {db_error}")
                    # قد تقرر إرجاع خطأ هنا لمنع المستخدم من المتابعة إذا فشل حفظ الحالة الأولية
                    return jsonify({'error': 'Database error saving initial subscription state.'}), 500

                return jsonify({'paypal_subscription_id': agreement.id, 'approve_url': approval_url}), 200
            else:
                app.logger.error("Could not get PayPal approval URL from agreement.")
                return jsonify({'error': 'Could not get PayPal approval URL.'}), 500
        else:
            app.logger.error(f"Error creating PayPal Billing Agreement: {agreement.error}")
            return jsonify({'error': 'Failed to create PayPal subscription.', 'details': agreement.error}), 500

    except Exception as e:
        app.logger.error(f"Exception in create_paypal_subscription: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/paypal-webhook', methods=['POST'])
def paypal_webhook():
    # --- التحقق من صحة الـ Webhook (ضروري للإنتاج) ---
    # PAYPAL_WEBHOOK_ID = os.getenv('PAYPAL_WEBHOOK_ID')
    # if not PAYPAL_WEBHOOK_ID:
    #     app.logger.error("PAYPAL_WEBHOOK_ID not set.")
    #     return jsonify({'status': 'configuration_error'}), 500
    # try:
    #     # تحتاج إلى request.data (بايتات) و request.headers (قاموس)
    #     event_verify = paypalrestsdk.WebhookEvent.verify(
    #         request.data.decode('utf-8'), # أو اتركها request.data إذا كانت SDK تتوقع بايتات
    #         dict(request.headers), 
    #         PAYPAL_WEBHOOK_ID
    #     )
    #     if not event_verify:
    #         app.logger.warning("Webhook verification failed.")
    #         return jsonify({'status': 'verification_failed'}), 400
    #     app.logger.info("Webhook verified successfully.")
    # except Exception as e:
    #     app.logger.error(f"Webhook verification exception: {e}")
    #     return jsonify({'status': 'verification_exception'}), 400
    # --------------------------------------------------

    try:
        event_json_payload = request.get_json()
        event_type = event_json_payload.get('event_type')
        resource = event_json_payload.get('resource')
        app.logger.info(f"Received PayPal Webhook - Event Type: {event_type}")
    except Exception as e:
        app.logger.error(f"Error parsing webhook JSON: {e}")
        return jsonify({'status': 'json_parse_error'}), 400

    if not resource:
        app.logger.error("Webhook resource data is missing.")
        return jsonify({'status': 'missing_resource_data'}), 400

    # --- التعامل مع أنواع الأحداث ---
    # معرفات خطط PayPal الفعلية التي أنشأتها في لوحة تحكم PayPal
    PAYPAL_PRO_PLAN_ID = os.getenv("PAYPAL_PRO_PLAN_ID_FROM_DASHBOARD") 
    PAYPAL_PREMIUM_PLAN_ID = os.getenv("PAYPAL_PREMIUM_PLAN_ID_FROM_DASHBOARD")

    if event_type == 'BILLING.SUBSCRIPTION.ACTIVATED':
        paypal_sub_id_final = resource.get('id') # هذا هو I-XXXXXXXXXXXX
        paypal_plan_id_from_event = resource.get('plan_id')
        status = resource.get('status') # يجب أن يكون "ACTIVE"
        
        # قد تحتاج لجلب تفاصيل اتفاقية الفوترة للحصول على تواريخ البدء/الانتهاء إذا لم تكن مباشرة في هذا الحدث
        # agreement_details = resource.get('billing_agreement_options', {}).get('agreement_details', {}) # مسار محتمل
        # start_time_str = agreement_details.get('start_time') # أو من 'create_time' في resource
        # next_billing_date_str = agreement_details.get('next_billing_date')
        
        # تحويل هذه التواريخ إلى كائنات datetime ثم إلى صيغة ISO لـ Supabase
        # start_date_iso = None
        # end_date_iso = None
        # if start_time_str:
        #     start_date_iso = datetime.datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M:%SZ').isoformat()
        # if next_billing_date_str:
        #    end_date_iso = datetime.datetime.strptime(next_billing_date_str, '%Y-%m-%dT%H:%M:%SZ').isoformat()

        plan_name_to_store = "unknown"
        if paypal_plan_id_from_event == PAYPAL_PRO_PLAN_ID:
            plan_name_to_store = "pro"
        elif paypal_plan_id_from_event == PAYPAL_PREMIUM_PLAN_ID:
            plan_name_to_store = "premium"
        
        app.logger.info(f"Activating subscription: {paypal_sub_id_final}, Plan: {plan_name_to_store} ({paypal_plan_id_from_event})")
        try:
            # تحديث السجل الذي يجب أن يكون قد تم إنشاؤه في /create-paypal-subscription
            update_payload = {
                'status': 'active',
                'plan_name': plan_name_to_store,
                # 'start_date': start_date_iso, # أضف إذا حصلت عليه
                # 'end_date': end_date_iso,     # أضف إذا حصلت عليه
                'updated_at': 'now()'
            }
            # استخدم paypal_sub_id_final الذي هو معرف الاشتراك الفعلي من PayPal
            update_result = supabase_service_client.table('subscriptions')\
                .update(update_payload)\
                .eq('paypal_subscription_id', paypal_sub_id_final)\
                .execute()

            if not update_result.data or len(update_result.data) == 0:
                 app.logger.warning(f"No existing subscription found to activate for PayPal ID {paypal_sub_id_final}. This should not happen if pre-creation worked.")
                 # يمكنك محاولة إنشاء سجل جديد هنا كحل احتياطي إذا لم تجد السجل "pending"
                 # ولكن هذا يشير إلى مشكلة في التدفق إذا لم يتم العثور عليه.
            else:
                app.logger.info(f"Subscription {paypal_sub_id_final} activated in Supabase.")

        except Exception as db_error:
            app.logger.error(f"DB error activating subscription {paypal_sub_id_final}: {db_error}")
            
    elif event_type == 'PAYMENT.SALE.COMPLETED':
        billing_agreement_id = resource.get('billing_agreement_id') # هذا هو معرف الاشتراك الفعلي
        if billing_agreement_id:
            app.logger.info(f"Payment completed for subscription: {billing_agreement_id}. Consider updating end_date.")
            # هنا يمكنك جلب تفاصيل الاشتراك من PayPal باستخدام billing_agreement_id
            # للحصول على تاريخ الفوترة التالي الجديد وتحديث 'end_date' في Supabase.
            # try:
            #     agreement = paypalrestsdk.BillingAgreement.find(billing_agreement_id)
            #     if agreement:
            #         next_billing_date_str = agreement.agreement_details.next_billing_date
            #         # ... قم بالتحويل والتحديث ...
            # except Exception as e:
            #     app.logger.error(f"Error fetching agreement details for {billing_agreement_id}: {e}")

    elif event_type in ['BILLING.SUBSCRIPTION.CANCELLED', 'BILLING.SUBSCRIPTION.EXPIRED', 'BILLING.SUBSCRIPTION.SUSPENDED']:
        paypal_subscription_id_from_event = resource.get('id')
        new_paypal_status = resource.get('status', 'unknown').lower()
        
        app_status = 'inactive' # افتراضي
        if new_paypal_status == 'cancelled':
            app_status = 'cancelled'
        elif new_paypal_status == 'suspended':
            app_status = 'suspended'
        
        app.logger.info(f"Subscription event: {paypal_subscription_id_from_event}, PayPal Status: {new_paypal_status}, App Status: {app_status}")
        try:
            supabase_service_client.table('subscriptions').update({
                'status': app_status,
                'updated_at': 'now()'
            }).eq('paypal_subscription_id', paypal_subscription_id_from_event).execute()
            app.logger.info(f"Updated Supabase subscription {paypal_subscription_id_from_event} to status {app_status}.")
        except Exception as db_error:
            app.logger.error(f"DB error on subscription event for {paypal_subscription_id_from_event}: {db_error}")
            
    return jsonify({'status': 'webhook_received'}), 200


@app.route('/payment/success/paypal')
def payment_success_paypal():
    # BA-XXXXXXXXXXXXXX (معرف اتفاقية الفوترة)
    # يجب أن يكون هو نفسه الذي تم تخزينه كـ paypal_subscription_id في البداية
    token = request.args.get('token') 
    if token:
        try:
            # تنفيذ اتفاقية الفوترة إذا لم يتم تفعيلها تلقائيًا
            # هذا قد يكون ضروريًا لبعض تدفقات PayPal
            agreement = paypalrestsdk.BillingAgreement.execute(token)
            if agreement.state.lower() == "active":
                app.logger.info(f"Billing Agreement {token} executed and is active.")
                flash("تم تفعيل اشتراكك بنجاح!", "success")
                # الـ webhook هو المصدر الرئيسي للتحديث، لكن يمكننا التوجيه هنا
                return redirect(url_for('dashboard')) 
            else:
                app.logger.warning(f"Billing Agreement {token} executed but state is {agreement.state}.")
                flash("يتم معالجة اشتراكك. سيتم تحديث حالتك قريبًا.", "info")
        except Exception as e:
            app.logger.error(f"Error executing billing agreement {token}: {e}")
            flash("حدث خطأ أثناء تأكيد اشتراكك. يرجى التحقق من حالة اشتراكك لاحقًا أو الاتصال بالدعم.", "danger")
    else:
        flash("يتم معالجة اشتراكك. سيتم تحديث حالتك قريبًا.", "info")
    return redirect(url_for('pricing_page'))


@app.route('/payment/cancel/paypal')
def payment_cancel_paypal():
    flash("تم إلغاء عملية الاشتراك أو حدث خطأ.", "warning")
    return redirect(url_for('pricing_page'))


# ===== ميزات تتطلب اشتراكًا (مثال) =====
@app.route('/pro-feature')
def pro_feature():
    if 'user_session' not in session:
        flash("الرجاء تسجيل الدخول للوصول لهذه الميزة.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user_session']['id']
    try:
        response = supabase_service_client.table('subscriptions').select('status, plan_name')\
            .eq('user_id', user_id)\
            .eq('status', 'active')\
            .in_('plan_name', ['pro', 'premium'])\
            .maybe_single().execute()
            
        if not response.data:
            flash("هذه الميزة تتطلب اشتراك برو أو بريميوم نشط.", "warning")
            return redirect(url_for('pricing_page'))
    except Exception as e:
        app.logger.error(f"Error checking pro-feature access for user {user_id}: {e}")
        flash("حدث خطأ أثناء التحقق من اشتراكك.", "danger")
        return redirect(url_for('pricing_page'))
        
    return render_template('pro_feature_page.html') # افترض أن لديك هذا القالب


if __name__ == '__main__':
    # مهم: لا تستخدم app.run(debug=True) في الإنتاج. استخدم Gunicorn.
    # Render ستستخدم Gunicorn بناءً على أمر البدء الذي حددته.
    app.run(debug=True, port=os.getenv("PORT", 5000))