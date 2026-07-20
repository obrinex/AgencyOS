"""Pure domain layer.

Nothing in this package performs I/O, imports a repository, touches `db`, or
references a country/currency/timezone/phone-prefix literal. Everything here
is a plain function over plain data, which is what makes it the one layer in
this repo that is worth unit testing.
"""
