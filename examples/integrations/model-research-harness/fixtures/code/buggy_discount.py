def discounted_total(price, quantity, discount_percent):
    """Return a discounted line total.

    Known bug for the harness: negative quantity is not rejected.
    """
    if price < 0:
        raise ValueError("price must be non-negative")
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount_percent must be between 0 and 100")
    subtotal = price * quantity
    return subtotal * (1 - discount_percent / 100)
