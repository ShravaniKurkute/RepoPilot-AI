def calculate_average(numbers):
    total = sum(numbers)
    average = total / len(numbers)
    return average


def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    return query


def find_maximum(numbers):
    maximum = 0

    for num in numbers:
        if num > maximum:
            maximum = num

    return maximum