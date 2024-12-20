from django.db import models

from store.models import Product
from userauths.models import User


TYPE = (
    ("New Order", "New Order"),
    ("Item Shipped", "Item Shipped"),
    ("Item Delivered", "Item Delivered"),
)

class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist")
    
    class Meta:
        verbose_name_plural = "Wishlist"
    
    def __str__(self):
        if self.product.name:
            return self.product.name
        else:
            return "Wishlist"
        
class Address(models.Model):
    DELIVERY_CHOICES = [
        ('econt', 'Econt'),
        ('speedy', 'Speedy'),
        ('personal', 'Personal'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    full_name = models.CharField(max_length=200, null=True, blank=True, default=None)
    mobile = models.CharField(max_length=50, null=True, blank=True, default=None)
    email = models.CharField(max_length=100, null=True, blank=True, default=None)
    delivery_method = models.CharField(
        max_length=10, 
        choices=DELIVERY_CHOICES, 
        null=True, 
        blank=True
    )
    city = models.CharField(max_length=100, null=True, blank=True, default=None)
    address = models.CharField(max_length=100, null=True, blank=True, default=None)


    class Meta:
        verbose_name_plural = "Customer Addresses"

    def __str__(self):
        return self.full_name



class Notifications(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    type = models.CharField(max_length=100, choices=TYPE, default=None)
    seen = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Notification"
    
    def __str__(self):
        return self.type
