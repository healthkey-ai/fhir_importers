## Comments

Follow "Code As Documentation" principle.

Self-Documenting Code:
The goal is to write code that expresses intent clearly via intention-revealing names (methods, classes, and variables).
Code Tells You How, Comments Tell You Why:
If you must use comments, they should explain the why (business logic constraints, trade-offs, or context) rather than the what.

No need in package-level and file-level comments

Class comment should explain the purpose, responsibility and boundaries.

Method comments usually are brief one-liners.

Only tricky logic which is not self-evident from the code itself should be commented.
If you find yourself writing a comment to explain what the code does,
consider refactoring the code to make it more readable instead.
