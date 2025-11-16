# Contributing to Bond Relative Value Analysis System

Thank you for considering contributing to this project! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and professional in all interactions
- Focus on constructive feedback
- Help create a welcoming environment for all contributors

## How to Contribute

### Reporting Bugs

1. **Check existing issues** to avoid duplicates
2. **Create a detailed bug report** including:
   - Clear description of the issue
   - Steps to reproduce
   - Expected vs. actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs or error messages

### Suggesting Enhancements

1. **Open an issue** with the `enhancement` label
2. **Describe the feature** clearly:
   - Use case and benefits
   - Proposed implementation approach
   - Any potential drawbacks or considerations

### Pull Requests

1. **Fork the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Bonds.git
   cd Bonds
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Update documentation as needed

4. **Test your changes**
   ```bash
   python app.py
   # Test manually in the browser
   ```

5. **Commit with clear messages**
   ```bash
   git commit -m "Add feature: description of what was added"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Open a Pull Request**
   - Provide a clear description
   - Reference any related issues
   - Explain what was changed and why

## Development Guidelines

### Code Style

- Follow PEP 8 for Python code
- Use descriptive variable and function names
- Keep functions focused and single-purpose
- Add docstrings to functions and classes

Example:
```python
def calculate_sofr_swap_rate(tenor, sofr_spread_data):
    """
    Calculates the SOFR Swap Rate based on the formula:
    SOFR Swap Rate = Treasury Rate - (T_SOFR_SPREAD)

    Args:
        tenor: Years to maturity (e.g., "1", "5", "10")
        sofr_spread_data: Dict containing T_RATE and T_SOFR_SPREAD

    Returns:
        float: SOFR swap rate in decimal format
    """
    # Implementation...
```

### Project Structure

- **app.py**: Main Flask routes only, delegate logic to services
- **services/**: Business logic, modular and testable
- **normalization_engine.py**: Pure calculation functions
- **templates/**: UI code only, minimal embedded logic

### Adding New Features

#### Adding a New Currency

1. Update `config.py`:
   ```python
   FUNDING_RATES = {
       'JPY': 0.0010,  # Add new currency
   }
   ```

2. Add fair value curves for the currency

#### Adding a New Data Source

1. Update `services/realtime_data_service.py`
2. Add source to the prompt's priority list
3. Update data source attribution in response

#### Adding a New Benchmark

1. Update `config.py` with the new benchmark rate
2. Update `normalization_engine.py` if new calculations needed
3. Update UI to display the new benchmark

### Testing

Currently, the project uses manual testing. Future improvements:

1. **Unit Tests**: Add tests for calculation functions
   ```bash
   pytest tests/
   ```

2. **Integration Tests**: Test API endpoints
3. **End-to-End Tests**: Test full workflows

### Commit Message Guidelines

Use clear, descriptive commit messages:

- **feat**: New feature
  ```
  feat: add support for GBP currency bonds
  ```

- **fix**: Bug fix
  ```
  fix: correct SOFR equivalent calculation for float bonds
  ```

- **docs**: Documentation changes
  ```
  docs: update README with installation instructions
  ```

- **refactor**: Code refactoring
  ```
  refactor: extract market data fetching into separate service
  ```

- **style**: Code style changes (formatting, etc.)
  ```
  style: format code according to PEP 8
  ```

- **test**: Adding or updating tests
  ```
  test: add unit tests for normalization engine
  ```

## Financial Domain Knowledge

If contributing financial calculations:

1. **Cite sources** for formulas and methodologies
2. **Add comments** explaining the financial logic
3. **Include examples** in docstrings
4. **Test with realistic data**

Example:
```python
def calculate_usd_hedged_yield(local_yield, ccy, funding_rates):
    """
    Calculates USD-Hedged Yield using Covered Interest Parity.

    Formula: Y_Hedged = Y_Local + (r_USD - r_FCY)

    Source: "Fixed Income Mathematics" by Frank J. Fabozzi

    Example:
        >>> calculate_usd_hedged_yield(0.0400, 'EUR', {'USD': 0.0500, 'EUR': 0.0400})
        0.0500  # 4% EUR yield + (5% USD - 4% EUR) = 5% hedged
    """
```

## Questions?

- Open an issue with the `question` label
- Reach out to maintainers
- Check existing documentation and issues

## Recognition

Contributors will be acknowledged in:
- README.md
- Release notes
- Project documentation

Thank you for contributing! 🎉
