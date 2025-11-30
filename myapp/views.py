from django.shortcuts import render, redirect
from .models import Products
from .forms import ProductForm
from django.http import JsonResponse
from .models import Products
# Create your views here.

def home(request):
    return render(request, 'home.html')

def base(request):
    return render(request, 'base.html')


def add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'add_products.html', {'form': form})

def product_list(request):
    products = Products.objects.all()
    return render(request, 'product_list.html', {'products': products})

def product_detail(request, pk):
    product = Products.objects.get(pk=pk)
    return render(request, 'product_detail.html', {'product': product})

def edit_product(request, pk):
    product= Products.objects.get(pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'edit_product.html', {'form': form})

def delete_product(request, pk):
    product = Products.objects.get(pk=pk)
    if request.method == 'POST':
        product.delete()
        return redirect('product_list')
    return render(request, 'delete_product.html', {'product': product})



def search_suggest(request):
    q = request.GET.get("q", "")

    products = Products.objects.filter(name__icontains=q)

    results = [
        {
            "id": p.id,
            "name": p.name,
            "price": float(p.price),
            "image": p.image.url if p.image else ""
        }
        for p in products
    ]

    return JsonResponse(results, safe=False)




from django.http import JsonResponse
from .models import Products

def get_cart(request):
    cart = request.session.get("cart", {})
    return cart


def save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


# ➕ ADD PRODUCT OR INCREASE QTY
def cart_add(request, pk):
    cart = get_cart(request)

    pk = str(pk)
    if pk in cart:
        cart[pk]["quantity"] += 1
    else:
        cart[pk] = {"quantity": 1}

    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


# ➖ REDUCE QTY
def cart_reduce(request, pk):
    cart = get_cart(request)
    pk = str(pk)

    if pk in cart:
        cart[pk]["quantity"] -= 1
        if cart[pk]["quantity"] <= 0:
            del cart[pk]

    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


# ❌ REMOVE PRODUCT COMPLETELY
def cart_remove(request, pk):
    cart = get_cart(request)
    pk = str(pk)

    if pk in cart:
        del cart[pk]

    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


# 📦 FULL CART DETAILS (SUMMARY)
def get_cart_summary(cart):
    products = Products.objects.filter(id__in=cart.keys())

    cart_items = []
    total_price = 0
    total_qty = 0

    for product in products:
        qty = cart[str(product.id)]["quantity"]
        subtotal = qty * float(product.price)
        total_price += subtotal
        total_qty += qty

        cart_items.append({
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "quantity": qty,
            "subtotal": subtotal,
            "image": product.image.url if product.image else "",
        })

    return {
        "items": cart_items,
        "total_price": total_price,
        "total_qty": total_qty,
    }


# 🛒 GET CART COUNT FOR NAVBAR
def cart_count(request):
    cart = get_cart(request)
    total_qty = sum(item["quantity"] for item in cart.values())
    return JsonResponse({"count": total_qty})

def checkout(request):
    cart = request.session.get("cart", {})

    if not cart:
        return render(request, "checkout_empty.html")

    products = Products.objects.filter(id__in=cart.keys())

    cart_items = []
    total_price = 0

    for product in products:
        qty = cart[str(product.id)]["quantity"]
        subtotal = qty * float(product.price)
        total_price += subtotal

        cart_items.append({
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "quantity": qty,
            "subtotal": subtotal,
            "image": product.image.url if product.image else "",
        })

    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        address = request.POST.get("address")
        phone = request.POST.get("phone")

        # Clear cart
        request.session["cart"] = {}
        request.session.modified = True

        return render(request, "checkout_success.html", {
            "name": name,
            "total_price": total_price
        })

    return render(request, "checkout.html", {
        "cart_items": cart_items,
        "total_price": total_price
    })
def checkout_success(request):
    return render(request, "checkout_success.html")
from django.core.mail import send_mail
from django.conf import settings
from .models import Order, OrderItem

def checkout(request):
    cart = request.session.get("cart", {})

    if not cart:
        return render(request, "checkout_empty.html")

    products = Products.objects.filter(id__in=cart.keys())

    cart_items = []
    total_price = 0

    for product in products:
        qty = cart[str(product.id)]["quantity"]
        subtotal = qty * float(product.price)
        total_price += subtotal

        cart_items.append({
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "quantity": qty,
            "subtotal": subtotal,
            "image": product.image.url if product.image else "",
        })

    # FORM SUBMISSION
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        address = request.POST.get("address")
        phone = request.POST.get("phone")

        # SAVE ORDER
        order = Order.objects.create(
            customer_name=name,
            email=email,
            phone=phone,
            address=address,
            total_price=total_price
        )

        # SAVE ORDER ITEMS + REDUCE PRODUCT STOCK
        for product in products:
            qty = cart[str(product.id)]["quantity"]
            subtotal = qty * float(product.price)

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=qty,
                price=product.price,
                subtotal=subtotal
            )

            # REDUCE STOCK
            if hasattr(product, "stock"):  # if stock exists in model
                product.stock -= qty
                product.save()

        # SEND EMAIL RECEIPT
        send_mail(
            subject="Your Order Receipt",
            message=f"Thank you for your order #{order.id}.\nTotal: ${total_price}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True
        )

        # CLEAR CART
        request.session["cart"] = {}
        request.session.modified = True

        return render(request, "checkout_success.html", {
            "name": name,
            "total_price": total_price,
            "order_id": order.id
        })

    return render(request, "checkout.html", {
        "cart_items": cart_items,
        "total_price": total_price
    })

def checkout_empty(request):
    return render(request, "checkout_empty.html")
