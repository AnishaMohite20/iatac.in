document.addEventListener('DOMContentLoaded', function () {
    const payNowBtn = document.getElementById('payNowBtn');
    const paymentModal = document.getElementById('paymentModal');
    const closeModal = document.getElementById('closeModal');
    const paymentForm = document.getElementById('paymentForm');
    const serviceSelect = document.getElementById('u_service');
    const amountInput = document.getElementById('u_amount');

    // Configuration
    // CHANGE THIS TO YOUR GODADDY BACKEND URL WHEN DEPLOYING
    // Example: const API_BASE_URL = "https://your-app-name.godaddysites.com";
    // Configuration
    const API_BASE_URL = "/api"; // Relative path for Vercel (works on same domain)

    // Amount Mapping
    const prices = {
        "Annual Fee (All)": 5000,
        "HR Services Company Membership": 5000,
        "HR Consultants Membership": 3000,
        "Corporates Membership": 15000,
        "Demo Service": 1
    };

    // ... (Modal logic remains same)

    // Handle Form Submission
    paymentForm.onsubmit = async function (e) {
        e.preventDefault();

        const userData = {
            name: document.getElementById('u_name').value,
            phone: document.getElementById('u_phone').value,
            email: document.getElementById('u_email').value,
            service: serviceSelect.value
        };

        try {
            // 1. Create Order
            const response = await fetch(`${API_BASE_URL}/create_order`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(userData)
            });

            if (!response.ok) throw new Error('Failed to create order');
            const order = await response.json();

            // 2. Open Razorpay
            const options = {
                "key": "rzp_live_RUv2nx9Eg3xoQf",
                "amount": order.amount,
                "currency": "INR",
                "name": "IATAC",
                "description": userData.service,
                "image": "/images/logo-iatac.png",
                "order_id": order.id,
                "handler": async function (response) {
                    const submitBtn = document.getElementById('submitPayment');
                    submitBtn.innerText = "Verifying Payment...";
                    submitBtn.disabled = true;

                    // 1. Verify Payment
                    const verifyResponse = await fetch(`${API_BASE_URL}/verify_payment`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_signature: response.razorpay_signature
                        })
                    });

                    const result = await verifyResponse.json();
                    if (result.status === "Success") {
                        const details = result.details;

                        // Show success state
                        document.getElementById('paymentForm').style.display = "none";
                        document.getElementById('paymentSuccess').style.display = "block";

                        // Handle Download Button (Base64)
                        document.getElementById('downloadReceiptBtn').onclick = function (e) {
                            e.preventDefault();
                            if (details.pdf_base64) {
                                const link = document.createElement('a');
                                link.href = `data:application/pdf;base64,${details.pdf_base64}`;
                                link.download = `Receipt_${details.payment_id}.pdf`;
                                link.click();
                            } else {
                                alert("Receipt generation failed, but payment was successful. Check your email.");
                            }
                        };
                    } else {
                        alert("Payment Verification Failed: " + (result.error || "Unknown error"));
                        submitBtn.innerText = "Proceed to Pay";
                        submitBtn.disabled = false;
                    }
                },
                "prefill": {
                    "name": userData.name,
                    "email": userData.email,
                    "contact": userData.phone
                },
                "theme": { "color": "#007bff" }
            };
            const rzp = new Razorpay(options);
            rzp.on('payment.failed', function (r) { alert("Payment Failed: " + r.error.description); });
            rzp.open();

        } catch (error) {
            console.error(error);
            alert("An error occurred: " + error.message);
        }
    }

    // Close Success State
    document.getElementById('closeSuccessBtn').onclick = function () {
        paymentModal.style.display = "none";
        // Reset for next time
        document.getElementById('paymentForm').style.display = "block";
        document.getElementById('paymentSuccess').style.display = "none";
        document.getElementById('paymentForm').reset();
        document.getElementById('u_amount').value = 0;
        const disp = document.getElementById('u_amount_display');
        if (disp) disp.innerText = "0";
        document.getElementById('submitPayment').innerText = "Proceed to Pay";
        document.getElementById('submitPayment').disabled = false;
    }

});


