def truthy(value):
    '''
    @return True if the value is a string like 'True' (etc), or the boolean True
    '''
    print(value)
    if isinstance(value, str):
        try:
            value = int(value)
            return value != 0
        except ValueError:
            return value.lower() in {'true', 't', 'yes', 'y'}
    elif isinstance(value, int):
        value != 0
    else:
        return value == True


def falsy(value):
    '''
    @return True if the value is a string like 'True' (etc), or if it is the boolean False
    '''
    return not truthy(value)
