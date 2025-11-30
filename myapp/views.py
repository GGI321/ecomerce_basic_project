from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from .models import Products, Order, OrderItem
from .forms import ProductForm


# -------------------------------
# Simple Page Views
# -------------------------------
def home(request):
    return render(request, 'home.html')


def base(request):
    return render(request, 'base.html')


# -------------------------------
# Product CRUD
# -------------------------------
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
    product = get_object_or_404(Products, pk=pk)
    return render(request, 'product_detail.html', {'product': product})


def edit_product(request, pk):
    product = get_object_or_404(Products, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'edit_product.html', {'form': form})


def delete_product(request, pk):
    product = get_object_or_404(Products, pk=pk)
    if request.method == 'POST':
        product.delete()
        return redirect('product_list')
    return render(request, 'delete_product.html', {'product': product})


# -------------------------------
# Search Suggest (AJAX)
# -------------------------------
def search_suggest(request):
    q = request.GET.get("q", "")
    products = Products.objects.filter(name__icontains=q)[:10]
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


# -------------------------------
# CART UTILITIES
# -------------------------------
def get_cart(request):
    return request.session.get("cart", {})


def save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


# -------------------------------
# CART: Add / Reduce / Remove
# -------------------------------
def cart_add(request, pk):
    cart = get_cart(request)
    pk = str(pk)
    product = get_object_or_404(Products, pk=pk)

    if pk in cart:
        cart[pk]["quantity"] += 1
    else:
        cart[pk] = {
            "name": product.name,
            "price": float(product.price),
            "image": product.image.url if product.image else "",
            "quantity": 1,
        }

    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


def cart_reduce(request, pk):
    cart = get_cart(request)
    pk = str(pk)

    if pk in cart:
        cart[pk]["quantity"] -= 1
        if cart[pk]["quantity"] <= 0:
            del cart[pk]

    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


def cart_remove(request, pk):
    cart = get_cart(request)
    pk = str(pk)
    if pk in cart:
        del cart[pk]
    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


# -------------------------------
# CART SUMMARY / COUNT
# -------------------------------
def get_cart_summary(cart):
    product_ids = [int(i) for i in cart.keys()] if cart else []
    products = Products.objects.filter(id__in=product_ids)

    cart_items = []
    total_price = 0
    total_qty = 0

    product_lookup = {p.id: p for p in products}

    for pid_str, item in cart.items():
        pid = int(pid_str)
        product = product_lookup.get(pid)

        if not product:
            continue

        qty = int(item.get("quantity", 0))
        price = float(product.price)
        subtotal = qty * price

        total_price += subtotal
        total_qty += qty

        cart_items.append({
            "id": product.id,
            "name": product.name,
            "price": round(price, 2),
            "quantity": qty,
            "subtotal": round(subtotal, 2),
            "image": product.image.url if product.image else "",
        })

    return {
        "items": cart_items,
        "total_price": round(total_price, 2),
        "total_qty": total_qty,
    }


def cart_count(request):
    cart = get_cart(request)
    total_qty = sum(int(item.get("quantity", 0)) for item in cart.values())
    return JsonResponse({"count": total_qty})


# -------------------------------
# CHECKOUT
# -------------------------------
def checkout(request):
    if request.method == "POST":
        print("POST RECEIVED")  # ADD THIS

    cart = get_cart(request)
    if not cart:
        return render(request, "checkout_empty.html")

    cart_items = []
    total_price = 0

    product_ids = [int(i) for i in cart.keys()]
    products = Products.objects.filter(id__in=product_ids)
    product_lookup = {p.id: p for p in products}

    for pid_str, item in cart.items():
        product = product_lookup.get(int(pid_str))
        if not product:
            continue

        qty = int(item["quantity"])
        price = float(product.price)
        subtotal = round(qty * price, 2)
        total_price += subtotal

        cart_items.append({
            "id": product.id,
            "name": product.name,
            "price": price,
            "quantity": qty,
            "subtotal": subtotal,
            "image": product.image.url if product.image else "",
        })

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address", "").strip()

        if not (name and email and phone and address):
            messages.error(request, "All fields are required.")
            return redirect("checkout")

        try:
            order = Order.objects.create(
                customer_name=name,
                email=email,
                phone=phone,
                address=address,
                total_price=0,
                created_at=timezone.now()
            )

            for ci in cart_items:
                product = product_lookup.get(ci["id"])

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=ci["quantity"],
                    price=Decimal(str(product.price)),
                    subtotal=Decimal(str(product.price)) * ci["quantity"]
                )

            order.update_total()

            try:
                send_mail(
                    f"Order #{order.id} Confirmation",
                    f"Thanks {order.customer_name}, your order #{order.id} has been placed.",
                    settings.DEFAULT_FROM_EMAIL,
                    [order.email],
                    fail_silently=True,
                )
            except:
                pass

            request.session["cart"] = {}
            request.session.modified = True

            return redirect("checkout_success")

        except Exception as e:
            print("CHECKOUT ERROR:", e)
            messages.error(request, "Order processing failed.")
            return redirect("checkout")

    return render(request, "checkout.html", {
        "cart_items": cart_items,
        "total_price": total_price
    })


def checkout_success(request):
    return render(request, "checkout_success.html")


def checkout_empty(request):
    return render(request, "checkout_empty.html")
