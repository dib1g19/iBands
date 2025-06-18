from customer import models as customer_models

def get_user_wishlist_products(request):
    if request.user.is_authenticated:
        return set(
            customer_models.Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
        )
    return set()