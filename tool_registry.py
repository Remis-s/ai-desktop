import os
import importlib.util
import traceback

SKILLS_DIR = os.path.join(
    os.path.dirname(__file__),
    "skills"
)


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def load_skills(self):
        self.tools.clear()

        if not os.path.exists(SKILLS_DIR):
            os.makedirs(SKILLS_DIR)

        for filename in os.listdir(SKILLS_DIR):

            if not filename.endswith(".py"):
                continue

            if filename.startswith("_"):
                continue

            path = os.path.join(
                SKILLS_DIR,
                filename
            )

            module_name = filename[:-3]

            try:
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    path
                )

                if spec is None or spec.loader is None:
                    print(
                        f"[SKIP] {filename}: "
                        f"module tidak dapat dimuat"
                    )
                    continue

                module = importlib.util.module_from_spec(
                    spec
                )

                spec.loader.exec_module(
                    module
                )

                if not hasattr(module, "TOOL"):
                    print(
                        f"[SKIP] {filename}: "
                        f"tidak punya TOOL"
                    )
                    continue

                tool = module.TOOL

                if not isinstance(tool, dict):
                    print(
                        f"[SKIP] {filename}: "
                        f"TOOL bukan dictionary"
                    )
                    continue

                required = [
                    "name",
                    "description",
                    "parameters",
                    "run"
                ]

                if not all(
                    key in tool
                    for key in required
                ):
                    print(
                        f"[SKIP] {filename}: "
                        f"format TOOL tidak lengkap"
                    )
                    continue

                if not callable(tool["run"]):
                    print(
                        f"[SKIP] {filename}: "
                        f"run bukan function"
                    )
                    continue

                tool_name = str(
                    tool["name"]
                ).strip()

                if not tool_name:
                    print(
                        f"[SKIP] {filename}: "
                        f"nama TOOL kosong"
                    )
                    continue

                self.tools[
                    tool_name
                ] = tool

                print(
                    f"[SKILL LOADED] "
                    f"{tool_name}"
                )

            except Exception:
                print(
                    f"[SKILL ERROR] "
                    f"{filename}"
                )
                traceback.print_exc()

    def reload(self):
        self.load_skills()

    def list_tools(self):
        result = []

        for name, tool in self.tools.items():

            result.append({
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"]
            })

        return result

    def has_tool(self, name):
        return name in self.tools

    def _normalize_result(
        self,
        tool_name,
        result
    ):
        """
        Memastikan hasil sebuah skill benar-benar
        boleh dianggap sukses.
        """

        if result is None:

            return {
                "success": False,
                "error": (
                    f"Tool '{tool_name}' "
                    f"tidak mengembalikan hasil."
                )
            }

        if not isinstance(
            result,
            dict
        ):

            return {
                "success": False,
                "error": (
                    f"Tool '{tool_name}' "
                    f"mengembalikan format "
                    f"yang tidak valid: "
                    f"{type(result).__name__}"
                )
            }

        # Jika skill secara eksplisit
        # mengatakan gagal.
        if result.get(
            "success"
        ) is False:

            return {
                "success": False,
                "error": str(
                    result.get("error")
                    or result.get("message")
                    or "Tool melaporkan kegagalan."
                )
            }

        # Jika ada field error,
        # anggap sebagai kegagalan.
        error = result.get(
            "error"
        )

        if error:

            return {
                "success": False,
                "error": str(error)
            }

        # Cegah skill buatan AI
        # menelan exception kemudian
        # mengembalikannya sebagai message.
        message = str(
            result.get("message")
            or ""
        ).strip()

        lowered = message.lower()

        failure_prefixes = (
            "error:",
            "error ",
            "failed:",
            "failed ",
            "failure:",
            "failure ",
            "gagal:",
            "gagal ",
            "tidak berhasil",
            "operation failed",
            "operation error",
            "unable to",
            "cannot ",
            "can't "
        )

        if lowered.startswith(
            failure_prefixes
        ):

            return {
                "success": False,
                "error": message
            }

        # Jika sampai sini,
        # hasil dianggap valid.
        return {
            "success": True,
            "result": result
        }

    def run_tool(
        self,
        name,
        arguments=None
    ):
        if arguments is None:
            arguments = {}

        if name not in self.tools:

            return {
                "success": False,
                "error": (
                    f"Tool '{name}' "
                    f"tidak ditemukan"
                )
            }

        try:
            result = self.tools[
                name
            ][
                "run"
            ](
                **arguments
            )

            return self._normalize_result(
                name,
                result
            )

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }


registry = ToolRegistry()