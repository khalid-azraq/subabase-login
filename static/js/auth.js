// static/js/auth.js

// التأكد من أن SUPABASE_URL و SUPABASE_KEY معرفة في النطاق العام
// عادة ما يتم تمريرها من خلال متغيرات <script> في HTML
if (typeof SUPABASE_URL === 'undefined' || typeof SUPABASE_KEY === 'undefined') {
    console.error('Supabase URL or Key is not defined. Make sure to pass them from your Flask template.');
    // يمكنك إضافة آلية لإيقاف التنفيذ أو عرض رسالة خطأ للمستخدم هنا
}

// تهيئة عميل Supabase وجعله متاحًا عالميًا
window.supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

// --- عناصر نموذج تسجيل الدخول ---
const loginForm = document.getElementById('login-form');
const loginButton = document.getElementById('login-button');
const emailLoginInput = document.getElementById('email-login');
const passwordLoginInput = document.getElementById('password-login');
const authMessageLoginDiv = document.getElementById('auth-message-login');

// --- عناصر نموذج إنشاء الحساب ---
const signupForm = document.getElementById('signup-form');
const signupButton = document.getElementById('signup-button');
const emailSignupInput = document.getElementById('email-signup');
const passwordSignupInput = document.getElementById('password-signup');
const confirmPasswordInput = document.getElementById('confirm-password');
const authMessageSignupDiv = document.getElementById('auth-message-signup');

/**
 * يعرض رسالة للمستخدم في حاوية محددة.
 * @param {string} message - الرسالة المراد عرضها.
 * @param {'success' | 'error'} type - نوع الرسالة (يؤثر على النمط).
 * @param {HTMLElement} targetDiv - عنصر الـ div الذي ستعرض فيه الرسالة.
 */
function showMessage(message, type = 'error', targetDiv) {
    if (targetDiv) {
        targetDiv.textContent = message;
        targetDiv.className = `message ${type}`; // e.g., 'message error' or 'message success'
        targetDiv.style.display = 'block';
    } else {
        console.warn("Target div for showMessage not provided or found.");
    }
}

/**
 * يخفي حاوية الرسائل المحددة.
 * @param {HTMLElement} targetDiv - عنصر الـ div الذي سيتم إخفاؤه.
 */
function hideMessage(targetDiv) {
    if (targetDiv) {
        targetDiv.style.display = 'none';
    } else {
        console.warn("Target div for hideMessage not provided or found.");
    }
}

// --- معالج إرسال نموذج تسجيل الدخول ---
if (loginForm) {
    loginForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        hideMessage(authMessageLoginDiv);
        if (!loginButton || !emailLoginInput || !passwordLoginInput) {
            console.error("Login form elements not found.");
            return;
        }

        loginButton.disabled = true;
        loginButton.textContent = 'جارٍ تسجيل الدخول...';

        const email = emailLoginInput.value;
        const password = passwordLoginInput.value;

        if (!email || !password) {
            showMessage('الرجاء إدخال البريد الإلكتروني وكلمة المرور.', 'error', authMessageLoginDiv);
            loginButton.disabled = false;
            loginButton.textContent = 'تسجيل الدخول';
            return;
        }

        try {
            const { data, error } = await window.supabaseClient.auth.signInWithPassword({
                email: email,
                password: password,
            });

            if (error) {
                console.error('Supabase login error:', error);
                let friendlyMessage = 'فشل تسجيل الدخول. ';
                if (error.message.includes('Invalid login credentials')) {
                    friendlyMessage += 'البريد الإلكتروني أو كلمة المرور غير صحيحة.';
                } else if (error.message.includes('Email not confirmed')) {
                    friendlyMessage += 'الرجاء تأكيد بريدك الإلكتروني أولاً.';
                } else {
                    friendlyMessage += 'يرجى المحاولة مرة أخرى لاحقًا.';
                }
                showMessage(friendlyMessage, 'error', authMessageLoginDiv);
                loginButton.disabled = false;
                loginButton.textContent = 'تسجيل الدخول';
                return;
            }

            if (data.session && data.user) {
                // تم تسجيل الدخول بنجاح في Supabase
                // الآن, أبلغ الخادم (Flask) لإنشاء جلسته الخاصة
                const response = await fetch('/set-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        access_token: data.session.access_token,
                        user: data.user
                    }),
                });

                if (response.ok) {
                    showMessage('تم تسجيل الدخول بنجاح! يتم توجيهك...', 'success', authMessageLoginDiv);
                    window.location.href = '/dashboard'; // توجيه إلى لوحة التحكم
                } else {
                    const errorData = await response.json();
                    console.error('Flask session error:', errorData);
                    showMessage('فشل تسجيل الدخول من جانب الخادم. حاول مرة أخرى.', 'error', authMessageLoginDiv);
                    await window.supabaseClient.auth.signOut(); // تسجيل الخروج من Supabase إذا فشلت جلسة Flask
                    loginButton.disabled = false;
                    loginButton.textContent = 'تسجيل الدخول';
                }
            } else {
                showMessage('حدث خطأ غير متوقع أثناء تسجيل الدخول.', 'error', authMessageLoginDiv);
                loginButton.disabled = false;
                loginButton.textContent = 'تسجيل الدخول';
            }

        } catch (err) {
            console.error('General error during login:', err);
            showMessage('حدث خطأ. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.', 'error', authMessageLoginDiv);
            loginButton.disabled = false;
            loginButton.textContent = 'تسجيل الدخول';
        }
    });
} else {
    // console.log("Login form not found on this page."); // اختياري: للتأكد عند التحميل
}

// --- معالج إرسال نموذج إنشاء الحساب ---
if (signupForm) {
    signupForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        hideMessage(authMessageSignupDiv);
        if (!signupButton || !emailSignupInput || !passwordSignupInput || !confirmPasswordInput) {
            console.error("Signup form elements not found.");
            return;
        }

        signupButton.disabled = true;
        signupButton.textContent = 'جارٍ إنشاء الحساب...';

        const email = emailSignupInput.value;
        const password = passwordSignupInput.value;
        const confirmPassword = confirmPasswordInput.value;

        if (!email || !password || !confirmPassword) {
            showMessage('الرجاء ملء جميع الحقول.', 'error', authMessageSignupDiv);
            signupButton.disabled = false;
            signupButton.textContent = 'إنشاء حساب';
            return;
        }

        if (password !== confirmPassword) {
            showMessage('كلمتا المرور غير متطابقتين.', 'error', authMessageSignupDiv);
            signupButton.disabled = false;
            signupButton.textContent = 'إنشاء حساب';
            return;
        }

        if (password.length < 6) { // مثال: تحقق أساسي لطول كلمة المرور
            showMessage('يجب أن تكون كلمة المرور 6 أحرف على الأقل.', 'error', authMessageSignupDiv);
            signupButton.disabled = false;
            signupButton.textContent = 'إنشاء حساب';
            return;
        }

        try {
            const { data, error } = await window.supabaseClient.auth.signUp({
                email: email,
                password: password,
            });

            if (error) {
                console.error('Supabase signup error:', error);
                let friendlyMessage = 'فشل إنشاء الحساب. ';
                if (error.message.includes('User already registered')) {
                    friendlyMessage += 'هذا البريد الإلكتروني مسجل بالفعل.';
                } else if (error.message.toLowerCase().includes('password should be at least 6 characters')) { // جعلها غير حساسة لحالة الأحرف
                    friendlyMessage += 'يجب أن تكون كلمة المرور 6 أحرف على الأقل.';
                } else {
                    friendlyMessage += 'يرجى المحاولة مرة أخرى لاحقًا.';
                }
                showMessage(friendlyMessage, 'error', authMessageSignupDiv);
                signupButton.disabled = false;
                signupButton.textContent = 'إنشاء حساب';
                return;
            }

            // تم إنشاء الحساب بنجاح
            // data.user سيكون null إذا كان تأكيد البريد الإلكتروني مطلوبًا ولم يتم تأكيده بعد، أو أن المستخدم موجود لكن لم يؤكد
            // data.session سيكون null أيضًا في هذه الحالة عادةً
            // data.user.identities.length === 0  يشير إلى أن المستخدم جديد وينتظر التأكيد
            // data.user موجود و data.user.email_confirmed_at هو null يشير إلى مستخدم موجود لم يؤكد
            
            let successMessage = 'تم إنشاء الحساب بنجاح!';
            if (data.user && (!data.user.email_confirmed_at && data.user.identities && data.user.identities.length === 0)) {
                successMessage += ' الرجاء التحقق من بريدك الإلكتروني لتأكيد الحساب قبل تسجيل الدخول.';
                showMessage(successMessage, 'success', authMessageSignupDiv);
                // لا تحاول إنشاء جلسة أو توجيه المستخدم
            } else if (data.session && data.user) {
                // تم إنشاء الحساب وتسجيل الدخول تلقائيًا (إذا لم يكن تأكيد البريد مطلوبًا أو تم تعطيله)
                const response = await fetch('/set-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        access_token: data.session.access_token,
                        user: data.user
                    }),
                });

                if (response.ok) {
                    successMessage += ' يتم توجيهك الآن إلى لوحة التحكم...';
                    showMessage(successMessage, 'success', authMessageSignupDiv);
                    window.location.href = '/dashboard';
                } else {
                    const errorData = await response.json();
                    console.error('Flask session error after signup:', errorData);
                    showMessage('نجح إنشاء الحساب، ولكن فشل تسجيل الدخول التلقائي. حاول تسجيل الدخول يدويًا.', 'error', authMessageSignupDiv);
                }
            } else if (data.user && !data.user.email_confirmed_at) {
                // المستخدم تم إنشاؤه أو موجود، ولكنه لم يؤكد بريده بعد
                successMessage += ' الرجاء التحقق من بريدك الإلكتروني لتأكيد الحساب قبل تسجيل الدخول.';
                showMessage(successMessage, 'success', authMessageSignupDiv);
            }
            else {
                // حالة غير متوقعة، ولكن لا تزال تعتبر نجاحًا جزئيًا إذا تم إنشاء المستخدم
                 showMessage(successMessage + ' قد تحتاج لتسجيل الدخول يدويًا.', 'success', authMessageSignupDiv);
            }

            signupButton.disabled = false;
            signupButton.textContent = 'إنشاء حساب';

        } catch (err) {
            console.error('General error during signup:', err);
            showMessage('حدث خطأ. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.', 'error', authMessageSignupDiv);
            signupButton.disabled = false;
            signupButton.textContent = 'إنشاء حساب';
        }
    });
} else {
    // console.log("Signup form not found on this page."); // اختياري: للتأكد عند التحميل
}

// يمكنك إضافة وظيفة checkUserSession هنا إذا أردت،
// ولكن تأكد من أنها لا تتعارض مع منطق التحميل الأولي للصفحات.
// async function checkUserSession() {
//     const { data: { session } } = await window.supabaseClient.auth.getSession();
//     if (session) {
//         // منطق للتعامل مع وجود جلسة نشطة في Supabase عند تحميل الصفحة
//         // مثلاً، إذا كنت في صفحة تسجيل الدخول، قد تحاول إنشاء جلسة Flask وتوجيه المستخدم
//         // console.log('Supabase session active on page load:', session);
//     }
// }
// window.addEventListener('DOMContentLoaded', checkUserSession); // استدعاء عند تحميل DOM