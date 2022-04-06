
class ConsoleUtil:
    @staticmethod
    def get_string(prompt, default=''):
        prompt = f'{prompt}(default {default}):'
        return input(prompt).strip()

    @staticmethod
    def get_valid_input_int(prompt, default=None):
        if default is not None:
            prompt = f'{prompt}(default {default}):'
        else:
            prompt = f'{prompt}:'
        while True:
            try:
                value = input(prompt).strip()
                if value:
                    return int(value)
                elif default is not None:
                    return default
                else:
                    print('Input illegal, try again.')
            except Exception as e:
                print('Input illegal, try again.')

    @staticmethod
    def get_yes_no(prompt, default=None, case_sensitive=False, yes_prompt='YES(Y)', no_prompt='NO(N)'):
        if default is not None:
            prompt = f'{prompt}({yes_prompt} or {no_prompt})(default {default}):'
        else:
            prompt = f'{prompt}({yes_prompt} or {no_prompt}):'

        yes_set = {'YES', 'Y'}
        no_set = {'NO', 'N'}

        while True:
            value = input(prompt).strip()

            if not value and default is not None:
                value = default

            if value:
                if not case_sensitive:
                    value = value.upper()

            if value in yes_set:
                return True
            elif value in no_set:
                return False
            else:
                print('Input illegal, try again.')
