# amp
(python2k python3k conda cpython?) application module packaging

# how to use
* win + conda
```
Z:\foo> python -m amp.cli config foobar.json
.. edit foobar.json ..
Z:\foo> python -m amp.cil compose foobar.json targets=PythonPackingConfiguration
```
* *nix + cython (experimental)
```
/foo $ python -m amp.cli config foobar.json
.. edit foobar.json ..
/foo $ python -m amp.cli compose foobar.json targets=PythonPackingConfiguration
```
