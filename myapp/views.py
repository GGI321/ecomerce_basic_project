from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from .models import Products, Order, OrderItem
from .forms import ProductForm


# -------------------------------
# Helpers
# -------------------------------
def _to_decimal(value):
    """Convert a value to Decimal safely."""
    return Decimal(str(value))


def _round_money(d: Decimal) -> Decimal:
    """Round to 2 decimal places using banker's rounding behavior."""
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# -------------------------------
# Simple Page Views
# -------------------------------
def home(request):
    products = Products.objects.all()
    return render(request, "home.html", {"products": products})


def base(request):
    return render(request, "base.html")


# -------------------------------
# Product CRUD
# -------------------------------
def add_product(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(request, "add_products.html", {"form": form})


def product_list(request):
    products = Products.objects.all()
    return render(request, "product_list.html", {"products": products})


def product_detail(request, pk):
    product = get_object_or_404(Products, pk=pk)
    return render(request, "product_detail.html", {"product": product})


def edit_product(request, pk):
    product = get_object_or_404(Products, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "edit_product.html", {"form": form})


def delete_product(request, pk):
    product = get_object_or_404(Products, pk=pk)
    if request.method == "POST":
        product.delete()
        return redirect("product_list")
    return render(request, "delete_product.html", {"product": product})


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
            # return float here for convenience on the frontend
            "price": float(_round_money(_to_decimal(p.price))),
            "image": p.image.url if p.image else "",
        }
        for p in products
    ]
    return JsonResponse(results, safe=False)


# -------------------------------
# CART UTILITIES
# -------------------------------
def get_cart(request):
    """
    Cart session structure:
    {
        "<product_id>": {
            "name": "Product name",
            "price": "9.99",   # stored as string to preserve precision
            "image": "/media/..",
            "quantity": 2
        },
        ...
    }
    """
    return request.session.get("cart", {})


def save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


# -------------------------------
# CART: Add / Reduce / Remove
# -------------------------------
def cart_add(request, pk):
    """
    Adds one unit of product pk to the session cart.
    """
    cart = get_cart(request)
    pk = str(pk)
    # fetch product with integer pk
    product = get_object_or_404(Products, pk=int(pk))

    if pk in cart:
        cart[pk]["quantity"] = int(cart[pk].get("quantity", 0)) + 1
    else:
        cart[pk] = {
            "name": product.name,
            # store as string (exact) to avoid float issues
            "price": str(product.price),
            "image": product.image.url if product.image else "",
            "quantity": 1,
        }

    save_cart(request, cart)
    return JsonResponse(get_cart_summary(cart))


def cart_reduce(request, pk):
    cart = get_cart(request)
    pk = str(pk)
    if pk in cart:
        cart[pk]["quantity"] = int(cart[pk].get("quantity", 0)) - 1
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
    """
    Returns a JSON-serializable summary of the cart.
    Uses Decimal for arithmetic, returns floats rounded to 2 decimals.
    """
    product_ids = [int(i) for i in cart.keys()] if cart else []
    products = Products.objects.filter(id__in=product_ids)
    product_lookup = {p.id: p for p in products}

    cart_items = []
    total_price = Decimal("0")
    total_qty = 0

    for pid_str, item in cart.items():
        try:
            pid = int(pid_str)
        except (TypeError, ValueError):
            continue

        product = product_lookup.get(pid)
        if not product:
            # If product no longer exists, skip (could also remove from session)
            continue

        qty = int(item.get("quantity", 0))
        # Prefer authoritative DB price (safer if prices changed)
        price = _to_decimal(product.price)
        subtotal = price * qty

        total_price += subtotal
        total_qty += qty

        cart_items.append(
            {
                "id": product.id,
                "name": product.name,
                # return floats (rounded) so frontend can display easily
                "price": float(_round_money(price)),
                "quantity": qty,
                "subtotal": float(_round_money(subtotal)),
                "image": product.image.url if product.image else "",
            }
        )

    return {
        "items": cart_items,
        "total_price": float(_round_money(total_price)),
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
    cart = get_cart(request)
    if not cart:
        return render(request, "checkout_empty.html")

    # Load products and build cart-items with Decimal arithmetic
    product_ids = [int(i) for i in cart.keys()]
    products = Products.objects.filter(id__in=product_ids)
    product_lookup = {p.id: p for p in products}

    cart_items = []
    total_price = Decimal("0")

    for pid_str, item in cart.items():
        try:
            pid = int(pid_str)
        except (TypeError, ValueError):
            continue

        product = product_lookup.get(pid)
        if not product:
            continue

        qty = int(item.get("quantity", 0))
        price = _to_decimal(product.price)
        subtotal = price * qty
        total_price += subtotal

        cart_items.append(
            {
                "id": product.id,
                "name": product.name,
                "price": price,  # keep Decimal here for server-side use
                "quantity": qty,
                "subtotal": subtotal,
                "image": product.image.url if product.image else "",
            }
        )

    # POST: create order
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
                total_price=Decimal("0"),
                created_at=timezone.now(),
            )

            # Create order items using DB product prices (Decimal)
            for ci in cart_items:
                product = product_lookup.get(ci["id"])
                if not product:
                    continue

                qty = int(ci["quantity"])
                price = _to_decimal(product.price)
                subtotal = price * qty

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price=price,
                    subtotal=subtotal,
                )

            # Let model calculate and save the total (assuming Order.update_total exists)
            order.update_total()

            # Send confirmation email (fail silently so it doesn't block)
            try:
                send_mail(
                    subject=f"Order #{order.id} Confirmation",
                    message=f"Thanks {order.customer_name}, your order #{order.id} has been placed.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[order.email],
                    fail_silently=True,
                )
            except Exception:
                # Intentionally ignore email errors
                pass

            # Clear cart
            request.session["cart"] = {}
            request.session.modified = True

            return redirect("checkout_success")

        except Exception as e:
            # Print full exception to server logs for debugging
            print("CHECKOUT ERROR:", e)
            messages.error(request, "Order processing failed.")
            return redirect("checkout")

    # Render checkout page; pass user-friendly total (rounded)
    context = {
        "cart_items": [
            {
                "id": c["id"],
                "name": c["name"],
                "price": float(_round_money(c["price"])),
                "quantity": c["quantity"],
                "subtotal": float(_round_money(c["subtotal"])),
                "image": c["image"],
            }
            for c in cart_items
        ],
        "total_price": float(_round_money(total_price)),
    }
    return render(request, "checkout.html", context)


def checkout_success(request):
    return render(request, "checkout_success.html")


def checkout_empty(request):
    return render(request, "checkout_empty.html")
