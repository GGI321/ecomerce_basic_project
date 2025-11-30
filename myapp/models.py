from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal


class Products(models.Model):
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to='products/')
    stock = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=10, decimal_places=2)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def reduce_stock(self, quantity):
        """Safely reduce stock and prevent negative values."""
        if quantity > self.stock:
            raise ValueError("Not enough stock available")
        self.stock -= quantity
        self.save()

    def increase_stock(self, quantity):
        self.stock += quantity
        self.save()


class Order(models.Model):
    customer_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    address = models.TextField()

    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

    def update_total(self):
        """Recalculate the total price from all items."""
        total = sum(item.subtotal for item in self.items.all())
        self.total_price = total
        self.save()


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(
        Products,
        on_delete=models.CASCADE,
        related_name="order_items"
    )

    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)  # price per item
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

    def save(self, *args, **kwargs):
        """Auto-calc subtotal and reduce product stock when item is created."""
        if not self.subtotal:
            self.subtotal = Decimal(self.quantity) * Decimal(self.price)

        # Reduce stock ONLY when creating (not updating)
        if not self.pk:
            self.product.reduce_stock(self.quantity)

        super().save(*args, **kwargs)

        # Update order total after saving
        self.order.update_total()
