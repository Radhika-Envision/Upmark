__all__ = ['undefined']

from sentinels import Sentinel


class Undefined(Sentinel):
    """
    Behaves similarly to JavaScript's `undefined`:

    bool(undefined) -> False
    undefined == None -> True
    undefined == undefined -> True
    undefined is None -> False
    undefined is undefined -> True
    """

    def __eq__(self, other):
        if isinstance(other, Undefined):
            return True
        if other is None:
            return True
        return False

    def __bool__(self):
        return False

    def __repr__(self):
        return 'undefined'


undefined = Undefined('undefined')
