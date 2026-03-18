# from __future__ import annotations

# import asyncio
# import copy
# import json
# from sweagent.timing_tracker import get_timing_tracker

# import logging
# import time
# from pathlib import Path, PurePosixPath
# from typing import Annotated, Any, Literal

# import yaml
# from jinja2 import Template
# from pydantic import BaseModel, ConfigDict, Field, model_validator
# from simple_parsing.helpers.fields import field
# from swerex.exceptions import BashIncorrectSyntaxError, CommandTimeoutError, SwerexException
# from tenacity import RetryError
# from typing_extensions import Self
# from unidiff import UnidiffParseError

# from sweagent import __version__, get_agent_commit_hash, get_rex_commit_hash, get_rex_version
# from sweagent.agent.action_sampler import AbstractActionSampler, ActionSamplerConfig
# from sweagent.agent.history_processors import DefaultHistoryProcessor, HistoryProcessor
# from sweagent.agent.hooks.abstract import AbstractAgentHook, CombinedAgentHook
# from sweagent.agent.models import (
#     AbstractModel,
#     HumanModel,
#     HumanThoughtModel,
#     InstanceStats,
#     ModelConfig,
#     get_model,
# )
# from sweagent.agent.problem_statement import ProblemStatement, ProblemStatementConfig
# from sweagent.agent.reviewer import (
#     ChooserRetryLoop,
#     RetryLoopConfig,
#     ReviewSubmission,
#     ScoreRetryLoop,
#     get_retry_loop_from_config,
# )
# from sweagent.environment.swe_env import SWEEnv
# from sweagent.exceptions import (
#     ContentPolicyViolationError,
#     ContextWindowExceededError,
#     CostLimitExceededError,
#     FormatError,
#     TotalCostLimitExceededError,
# )
# from sweagent.tools.parsing import (
#     ActionOnlyParser,
#     ThoughtActionParser,
# )
# from sweagent.tools.tools import ToolConfig, ToolHandler
# from sweagent.types import AgentInfo, AgentRunResult, StepOutput, Trajectory, TrajectoryStep
# from sweagent.utils.config import _convert_paths_to_abspath, _strip_abspath_from_dict
# from sweagent.utils.jinja_warnings import _warn_probably_wrong_jinja_syntax
# from sweagent.utils.log import get_logger
# from sweagent.utils.patch_formatter import PatchFormatter


# class TemplateConfig(BaseModel):
#     """This configuration is used to define almost all message templates that are
#     formatted by the agent and sent to the LM.
#     """

#     system_template: str = ""
#     instance_template: str = ""
#     next_step_template: str = "Observation: {{observation}}"

#     next_step_truncated_observation_template: str = (
#         "Observation: {{observation[:max_observation_length]}}<response clipped>"
#         "<NOTE>Observations should not exceeded {{max_observation_length}} characters. "
#         "{{elided_chars}} characters were elided. Please try a different command that produces less output "
#         "or use head/tail/grep/redirect the output to a file. Do not use interactive pagers.</NOTE>"
#     )
#     """Message template for when the agent's observation was truncated.
#     Available variables: `observation`, `max_observation_length`, `elided_chars`
#     """

#     max_observation_length: int = 100_000
#     """Truncate observation to this length if it exceeds it.
#     This in measured in characters, i.e., as `len(observation)`.
#     """

#     next_step_no_output_template: str = None  # type: ignore
#     """Template for the next step when the last output was empty. Defaults to next_step_template."""

#     strategy_template: str | None = None
#     demonstration_template: str | None = None

#     demonstrations: list[Path] = field(default_factory=list)
#     """Paths to demonstrations. If path is not absolute, it is assumed to be
#     relative to the SWE_AGENT_CONFIG_ROOT (if set) or the SWE-agent repository root
#     """

#     put_demos_in_history: bool = False
#     """If True, add demonstration to history instead of as a single message"""

#     disable_image_processing: bool = False
#     """If True, disable image processing for multimodal problem statements (i.e. SWEBenchMultimodalProblemStatement).
#     """

#     shell_check_error_template: str = (
#         "Your bash command contained syntax errors and was NOT executed. "
#         "Please fix the syntax errors and try again. This can be the result "
#         "of not adhering to the syntax for multi-line commands. Here is the output of `bash -n`:\n"
#         "{{bash_stdout}}\n{{bash_stderr}}"
#     )
#     """Message template for when the agent's bash command contains syntax errors.
#     Available variables: `bash_stdout`, `bash_stderr`
#     """

#     command_cancelled_timeout_template: str = (
#         "The command '{{command}}' was cancelled because it took more than {{timeout}} seconds. "
#         "Please try a different command that completes more quickly. "
#         "Note: A common source of this error is if the command is interactive or requires user input "
#         "(it is impossible to receive user input in the current environment, so the command will never complete)."
#     )
#     """Message template for when the agent's command was cancelled because it took too long.
#     Available variables: `timeout`, `command`
#     """

#     def model_post_init(self, __context):
#         self.demonstrations = _convert_paths_to_abspath(self.demonstrations)
#         if self.next_step_no_output_template is None:
#             self.next_step_no_output_template = self.next_step_template

#     @model_validator(mode="after")
#     def validate_template_jinja_syntax(self) -> Self:
#         template_fields = [field for field in self.model_fields.keys() if field.endswith("_template")]
#         for field in template_fields:
#             value = getattr(self, field)
#             _warn_probably_wrong_jinja_syntax(value)
#         return self

#     @model_validator(mode="after")
#     def warnings(self) -> Self:
#         logger = get_logger("swea-config", emoji="🔧")
#         if self.put_demos_in_history and self.demonstration_template is not None:
#             logger.warning("demonstration_template is ignored when put_demos_in_history is True")
#         if not self.system_template or not self.instance_template:
#             logger.warning(
#                 "system_template/instance_template is not set, using empty string. Perhaps you were"
#                 " overwriting the default config? See https://swe-agent.com/latest/usage/cl_tutorial/"
#                 " for more information. Note: You can ignore this warning in human mode."
#             )
#         return self


# class DefaultAgentConfig(BaseModel):
#     """This configuration object specifies the behavior of an agent."""

#     name: str = "main"
#     templates: TemplateConfig = Field(default_factory=TemplateConfig)
#     tools: ToolConfig = Field(default_factory=ToolConfig)
#     history_processors: list[HistoryProcessor] = Field(default_factory=lambda: [DefaultHistoryProcessor()])
#     model: ModelConfig = Field(description="Model options.")

#     max_requeries: int = 3
#     """Maximum number of times to requery the model after an error, such as a
#     formatting error, a blocked action, or a bash syntax error.
#     """
#     action_sampler: ActionSamplerConfig | None = None

#     type: Literal["default"] = "default"

#     # pydantic config
#     model_config = ConfigDict(extra="forbid")


# class ShellAgentConfig(BaseModel):
#     name: str = "main"
#     templates: TemplateConfig = Field(default_factory=TemplateConfig)
#     tools: ToolConfig = Field(default_factory=ToolConfig)
#     history_processors: list[HistoryProcessor] = Field(default_factory=lambda: [DefaultHistoryProcessor()])
#     model: ModelConfig = Field(description="Model options.")

#     max_requeries: int = 3
#     """Maximum number of times to requery the model after an error, such as a
#     formatting error, a blocked action, or a bash syntax error.
#     """

#     type: Literal["shell"] = "shell"

#     # pydantic config
#     model_config = ConfigDict(extra="forbid")


# class RetryAgentConfig(BaseModel):
#     name: str = "retry_main"
#     agent_configs: list[DefaultAgentConfig]
#     retry_loop: RetryLoopConfig
#     type: Literal["retry"] = "retry"
#     model_config = ConfigDict(extra="forbid")


# AgentConfig = Annotated[DefaultAgentConfig | RetryAgentConfig | ShellAgentConfig, Field(union_mode="left_to_right")]


# class _BlockedActionError(Exception):
#     """Raised when the agent's action is blocked"""


# class _RetryWithOutput(Exception):
#     """Used for internal control flow"""


# class _RetryWithoutOutput(Exception):
#     """Used for internal control flow"""


# class _ExitForfeit(Exception):
#     """Used for internal control flow"""


# class _TotalExecutionTimeExceeded(Exception):
#     """Used for internal control flow"""


# RETRY_WITH_OUTPUT_TOKEN = "###SWE-AGENT-RETRY-WITH-OUTPUT###"
# RETRY_WITHOUT_OUTPUT_TOKEN = "###SWE-AGENT-RETRY-WITHOUT-OUTPUT###"
# EXIT_FORFEIT_TOKEN = "###SWE-AGENT-EXIT-FORFEIT###"


# class AbstractAgent:
#     def __init__(self, *args, **kwargs):
#         model: AbstractModel
#         replay_config: BaseModel | None
#         logger: logging.Logger

#     @classmethod
#     def from_config(cls, config: AgentConfig) -> Self: ...

#     def add_hook(self, hook: AbstractAgentHook) -> None: ...

#     def get_trajectory_data(self) -> dict[str, Any]: ...

#     def step(self) -> StepOutput: ...

#     def run(self, *args, **kwargs) -> AgentRunResult: ...


# def get_agent_from_config(config: AgentConfig) -> AbstractAgent:
#     if config.type == "default":
#         return DefaultAgent.from_config(config)
#     elif config.type == "retry":
#         return RetryAgent.from_config(config)
#     elif config.type == "shell":
#         # Need to defer import to avoid circular dependency
#         from sweagent.agent.extra.shell_agent import ShellAgent

#         return ShellAgent.from_config(config)
#     else:
#         msg = f"Unknown agent type: {config.type}"
#         raise ValueError(msg)


# class RetryAgent(AbstractAgent):
#     def __init__(self, config: RetryAgentConfig):
#         # Always copy config to avoid shared state between different instances
#         self.config = config.model_copy(deep=True)
#         self._hooks = []
#         self._i_attempt = 0
#         self.logger = get_logger("swea-agent", emoji="🤠")
#         self._agent: DefaultAgent | None = None
#         self._attempt_data: list[dict[str, Any]] = []
#         self._total_instance_attempt_stats = InstanceStats()
#         """Note that total_instance_attempt_stats only accumulates the states of the sub-agent,
#         not the reviewer. Use self._total_instance_stats for the total stats.
#         """
#         self._chook = CombinedAgentHook()
#         self._traj_path: Path | None = None
#         self._problem_statement: ProblemStatement | None = None
#         self._env: SWEEnv | None = None
#         self._output_dir: Path | None = None
#         self._rloop: ScoreRetryLoop | ChooserRetryLoop | None = None

#     @property
#     def _total_instance_stats(self) -> InstanceStats:
#         assert self._rloop is not None
#         return self._total_instance_attempt_stats + self._rloop.review_model_stats

#     @classmethod
#     def from_config(cls, config: RetryAgentConfig) -> Self:
#         return cls(config)

#     def add_hook(self, hook: AbstractAgentHook) -> None:
#         self._chook.add_hook(hook)
#         self._hooks.append(hook)

#     def setup(
#         self, env: SWEEnv, problem_statement: ProblemStatement | ProblemStatementConfig, output_dir: Path = Path(".")
#     ) -> None:
#         """Setup the retry agent for a new problem instance.
#         This is mostly a bookkeeping step.
#         """
#         self._total_instance_attempt_stats = InstanceStats()
#         self._problem_statement = problem_statement
#         self._traj_path = output_dir / (self._problem_statement.id + ".traj")
#         self._env = env
#         self._output_dir = output_dir
#         self._rloop = get_retry_loop_from_config(self.config.retry_loop, problem_statement=problem_statement)

#     def _setup_agent(self) -> AbstractAgent:
#         """Setup the agent for the current attempt."""
#         # todo: Could select "best" agent config based on previous attempts if I run > number of set up configs
#         agent_config = self.config.agent_configs[self._i_attempt % len(self.config.agent_configs)].model_copy(deep=True)
#         remaining_budget = self.config.retry_loop.cost_limit - self._total_instance_stats.instance_cost
#         if remaining_budget < agent_config.model.per_instance_cost_limit:
#             self.logger.debug("Setting agent per-attempt cost limit to remaining budget: %s", remaining_budget)
#             agent_config.model.per_instance_cost_limit = remaining_budget
#         self._agent = DefaultAgent.from_config(agent_config)
#         for hook in self._hooks:
#             self._agent.add_hook(hook)
#         assert self._output_dir is not None
#         sub_agent_output_dir = self._output_dir / f"attempt_{self._i_attempt}"
#         assert self._problem_statement is not None
#         assert self._env is not None
#         self._agent.setup(env=self._env, problem_statement=self._problem_statement, output_dir=sub_agent_output_dir)
#         return self._agent

#     def _next_attempt(self) -> None:
#         """Prepare for the next attempt: Reset the environment and setup the next agent."""
#         assert self._env is not None
#         self._i_attempt += 1
#         self._env.hard_reset()
#         self._setup_agent()

#     def step(self) -> StepOutput:
#         """Step the agent of the current attempt.
#         Attempt autosubmit if an error occurs (though all errors should already be handled by the attempt agent).
#         """
#         assert self._agent is not None
#         # Failsafe cost check, this should not actually happen, because the sub-agent should have already been
#         # initialized with the correct cost limit to not exceed the total cost limit. Using factor of 1.1, because
#         # sub-agent might only catch the cost limit after attempting.
#         if self._total_instance_stats.instance_cost > 1.1 * self.config.retry_loop.cost_limit > 0:
#             msg = "Total instance cost exceeded cost limit. This should not happen, please report this. Triggering autosubmit."
#             self.logger.critical(msg)
#             return self._agent.attempt_autosubmission_after_error(step=StepOutput())
#         try:
#             step = self._agent.step()
#         except TotalCostLimitExceededError:
#             # Need to make sure that this error causes everything to stop
#             raise
#         except Exception as e:
#             msg = "Error in agent step: %s. This really shouldn't happen, please report this. Triggering autosubmit."
#             self.logger.critical(msg, e, exc_info=True)
#             step = self._agent.attempt_autosubmission_after_error(step=StepOutput())
#         return step

#     def _finalize_agent_run(self) -> None:
#         """Add the agent results to our list of results"""
#         assert self._agent is not None
#         self._agent.save_trajectory()
#         self._attempt_data.append(self._agent.get_trajectory_data())
#         self._total_instance_attempt_stats += self._agent.model.stats

#     def get_trajectory_data(self, choose: bool) -> dict[str, Any]:
#         """Get all data that we save in .traj files."""
#         assert self._rloop is not None

#         data = {
#             "attempts": self._attempt_data,
#         }

#         if choose:
#             try:
#                 best_attempt_idx = self._rloop.get_best()
#             except TotalCostLimitExceededError:
#                 raise
#             except Exception as e:
#                 self.logger.critical(f"Error getting best attempt index: {e}. Setting to 0.", exc_info=True)
#                 best_attempt_idx = 0
#             data |= copy.deepcopy(self._attempt_data[best_attempt_idx])  # type: ignore
#             data["info"]["best_attempt_idx"] = best_attempt_idx
#             data["info"]["rloop_model_stats"] = self._rloop.review_model_stats.model_dump()
#             # Overwrite model stats with total stats
#             data["info"]["model_stats"] = self._total_instance_stats.model_dump()
#             if isinstance(self._rloop, ChooserRetryLoop):
#                 data["info"]["chooser"] = (
#                     self._rloop._chooser_output.model_dump() if self._rloop._chooser_output else {}
#                 )
#         return data

#     def save_trajectory(self, choose: bool) -> None:
#         data = self.get_trajectory_data(choose=choose)
#         assert self._traj_path is not None
#         self._traj_path.write_text(json.dumps(data, indent=2))

#     def run(
#         self,
#         env: SWEEnv,
#         problem_statement: ProblemStatement | ProblemStatementConfig,
#         output_dir: Path = Path("."),
#     ) -> AgentRunResult:
#         """Run the agent on a problem instance. This method contains the
#         main loop that repeatedly calls `self._step` until the problem is solved.

#         Args:
#             env: The environment to run the agent on.
#             problem_statement: The problem statement to run the agent on.
#             output_dir: Directory to save the trajectory to
#         """
#         output_dir.mkdir(parents=True, exist_ok=True)
#         self.setup(env=env, problem_statement=problem_statement, output_dir=output_dir)
#         assert self._rloop is not None

#         # Run action/observation loop
#         self._chook.on_run_start()
#         step_output = StepOutput()
#         self._setup_agent()
#         assert self._agent is not None
#         while not step_output.done:
#             step_output = self.step()
#             self.save_trajectory(choose=False)
#             if step_output.done:
#                 self._rloop.on_submit(
#                     ReviewSubmission(
#                         trajectory=self._agent.trajectory,
#                         info=self._agent.info,
#                         model_stats=self._agent.model.stats,
#                     )
#                 )
#                 if isinstance(self._rloop, ScoreRetryLoop):
#                     self._agent.info["review"] = self._rloop.reviews[-1].model_dump()  # type: ignore
#                 self._finalize_agent_run()
#                 self.save_trajectory(choose=False)
#                 if self._rloop.retry():
#                     assert self._env is not None
#                     self._next_attempt()
#                     step_output.done = False
#         self.save_trajectory(choose=True)  # call again after we finalized
#         self._chook.on_run_done(trajectory=self._agent.trajectory, info=self._agent.info)

#         self.logger.info("Trajectory saved to %s", self._traj_path)

#         # Here we want to return the "global" information (e.g., submission should
#         # be the best submission instead of the last one, etc.), so we get it from the traj file
#         data = self.get_trajectory_data(choose=True)
#         return AgentRunResult(info=data["info"], trajectory=data["trajectory"])


# class DefaultAgent(AbstractAgent):
#     def __init__(
#         self,
#         *,
#         templates: TemplateConfig,
#         tools: ToolHandler,
#         history_processors: list[HistoryProcessor],
#         model: AbstractModel,
#         max_requeries: int = 3,
#         name: str = "main",
#         _catch_errors: bool = True,
#         _always_require_zero_exit_code: bool = False,
#         action_sampler_config: ActionSamplerConfig | None = None,
#     ):
#         """The agent handles the behaviour of the model and how it interacts with the environment.

#         To run the agent, either call `self.run` or `self.setup` and then `self.step` in a loop.
#         """
#         self._catch_errors = _catch_errors
#         self._always_require_zero_exit_code = _always_require_zero_exit_code
#         self.name = name
#         self.model = model
#         self.templates = templates
#         self.tools = tools
#         if isinstance(self.model, HumanThoughtModel):
#             self.tools.config.parse_function = ThoughtActionParser()
#         elif isinstance(self.model, HumanModel):
#             self.tools.config.parse_function = ActionOnlyParser()
#         self.history_processors = history_processors
#         self.max_requeries = max_requeries
#         self.logger = get_logger("swea-agent", emoji="🤠")
#         # Set in run method
#         self._env: SWEEnv | None = None
#         self._problem_statement: ProblemStatement | ProblemStatementConfig | None = None
#         self.traj_path: Path | None = None

#         #: The following three attributes collect the information about how the agent
#         #: solved the problem.
#         self.history = []
#         self._trajectory = []
#         self.info = AgentInfo()

#         self._chook = CombinedAgentHook()

#         self._replay_config: BaseModel | None = None
#         """This can be set to a RunSingleConfig from the Run instance whenever possible.
#         It can be used to replay the agent's trajectory in an environment.
#         """

#         self._action_sampler: AbstractActionSampler | None = None
#         if action_sampler_config is not None:
#             self._action_sampler = action_sampler_config.get(self.model, self.tools)

#         #: Count how many timeout errors have occurred consecutively. Kills agent
#         #: after 5 of them.
#         self._n_consecutive_timeouts = 0
#         self._total_execution_time = 0.0

#     @classmethod
#     def from_config(cls, config: DefaultAgentConfig) -> Self:
#         # To ensure that all models stay completely independent, we deepcopy the
#         # model config, because it lives on as a property in the model, tools, etc.
#         config = config.model_copy(deep=True)
#         model = get_model(config.model, config.tools)
#         return cls(
#             templates=config.templates,
#             tools=ToolHandler(config.tools),
#             history_processors=config.history_processors,
#             model=model,
#             max_requeries=config.max_requeries,
#             action_sampler_config=config.action_sampler,
#         )

#     def add_hook(self, hook: AbstractAgentHook) -> None:
#         """Add hook to agent"""
#         hook.on_init(agent=self)
#         self._chook.add_hook(hook)

#     # Properties
#     # ----------

#     @property
#     def trajectory(self) -> Trajectory:
#         return self._trajectory

#     @property
#     def replay_config(self) -> BaseModel | None:
#         return self._replay_config

#     @replay_config.setter
#     def replay_config(self, value: BaseModel):
#         # Do import here to avoid circular dependency
#         from sweagent.run.run_single import RunSingleConfig

#         self._replay_config = RunSingleConfig.model_validate(_strip_abspath_from_dict(value.model_dump()))

#     @property
#     def messages(self) -> list[dict[str, Any]]:
#         """Return the history of the agent for this attempt since the last reset,
#         processed through all history processors.
#         """
#         filtered_history = [entry for entry in self.history if entry["agent"] == self.name]  # type: ignore

#         # Chain the history processors
#         messages = filtered_history
#         for processor in self.history_processors:
#             messages = processor(messages)

#         return messages  # type: ignore

#     # Methods
#     # -------

#     def _append_history(self, item: dict[str, Any]) -> None:
#         """Adds an item to the history."""
#         self._chook.on_query_message_added(**item)
#         self.history.append(item)  # type: ignore

#     # def setup(
#     #     self,
#     #     env: SWEEnv,
#     #     problem_statement: ProblemStatement | ProblemStatementConfig,
#     #     output_dir: Path = Path("."),
#     # ) -> None:
#     #     """Setup the agent for a new instance. This includes
#     #     formatting the system message and adding demonstrations to the history.

#     #     This method is called by `self.run`.
#     #     """
#     #     output_dir.mkdir(parents=True, exist_ok=True)

#     #     # apply template configuration to multimodal problem statements
#     #     if hasattr(problem_statement, "type") and problem_statement.type == "swe_bench_multimodal":
#     #         from sweagent.agent.problem_statement import SWEBenchMultimodalProblemStatement

#     #         if isinstance(problem_statement, SWEBenchMultimodalProblemStatement):
#     #             # apply the global disable_image_processing setting if it's not explicitly set
#     #             if not problem_statement.disable_image_processing and self.templates.disable_image_processing:
#     #                 problem_statement.disable_image_processing = True

#     #     self._problem_statement = problem_statement
#     #     self._env = env
#     #     iid = self._problem_statement.id
#     #     self.logger.info("Setting up agent for instance %s", iid)

#     #     # Save/reset some attributes
#     #     self.traj_path = output_dir / (self._problem_statement.id + ".traj")
#     #     self.logger.info("Trajectory will be saved to %s", self.traj_path)

#     #     self._chook.on_tools_installation_started()
#     #     self.tools.install(self._env)
#     #     self._chook.on_setup_attempt()
#     #     self.info = AgentInfo()
#     #     self.info["swe_agent_hash"] = get_agent_commit_hash()
#     #     self.info["swe_agent_version"] = __version__
#     #     self.info["swe_rex_version"] = get_rex_version()
#     #     self.info["swe_rex_hash"] = get_rex_commit_hash()
#     #     assert self._env is not None
#     #     assert self._problem_statement is not None
#     #     self._env.set_env_variables({"PROBLEM_STATEMENT": self._problem_statement.get_problem_statement_for_env()})
#     #     self.add_system_message_to_history()
#     #     self.add_demonstrations_to_history()
#     #     self.add_instance_template_to_history(state=self.tools.get_state(self._env))
#     #     self._chook.on_setup_done()

#     def setup(
#     self,
#     env: SWEEnv,
#     problem_statement: ProblemStatement | ProblemStatementConfig,
#     output_dir: Path = Path("."),
# ) -> None:
#         """Setup the agent for a new instance. This includes
#         formatting the system message and adding demonstrations to the history.

#         This method is called by `self.run`.
#         """
#         output_dir.mkdir(parents=True, exist_ok=True)

#         # START TIMING: agent setup
#         tracker = get_timing_tracker()
#         setup_timer_key = tracker.start_timer("agent_setup", "agent.setup()")

#         try:
#             # apply template configuration to multimodal problem statements
#             if hasattr(problem_statement, "type") and problem_statement.type == "swe_bench_multimodal":
#                 from sweagent.agent.problem_statement import SWEBenchMultimodalProblemStatement

#                 if isinstance(problem_statement, SWEBenchMultimodalProblemStatement):
#                     if not problem_statement.disable_image_processing and self.templates.disable_image_processing:
#                         problem_statement.disable_image_processing = True

#             self._problem_statement = problem_statement
#             self._env = env
#             iid = self._problem_statement.id
#             self.logger.info("Setting up agent for instance %s", iid)

#             # Save/reset some attributes
#             self.traj_path = output_dir / (self._problem_statement.id + ".traj")
#             self.logger.info("Trajectory will be saved to %s", self.traj_path)

#             self._chook.on_tools_installation_started()
#             self.tools.install(self._env)
#             self._chook.on_setup_attempt()
#             self.info = AgentInfo()
#             self.info["swe_agent_hash"] = get_agent_commit_hash()
#             self.info["swe_agent_version"] = __version__
#             self.info["swe_rex_version"] = get_rex_version()
#             self.info["swe_rex_hash"] = get_rex_commit_hash()
#             assert self._env is not None
#             assert self._problem_statement is not None
#             self._env.set_env_variables({"PROBLEM_STATEMENT": self._problem_statement.get_problem_statement_for_env()})
#             self.add_system_message_to_history()
#             self.add_demonstrations_to_history()
#             self.add_instance_template_to_history(state=self.tools.get_state(self._env))
#             self._chook.on_setup_done()
#         finally:
#             # END TIMING: agent setup
#             tracker.end_timer(setup_timer_key, "agent_setup")  

#     def add_system_message_to_history(self) -> None:
#         """Add system message to history"""
#         assert self._problem_statement is not None
#         system_msg = Template(self.templates.system_template).render(**self._get_format_dict())
#         self.logger.info(f"SYSTEM ({self.name})\n{system_msg}")
#         self._append_history(
#             {"role": "system", "content": system_msg, "agent": self.name, "message_type": "system_prompt"}
#         )

#     def add_demonstrations_to_history(self) -> None:
#         """Add demonstrations to history"""
#         for demonstration_path in self.templates.demonstrations:
#             self._add_demonstration_to_history(demonstration_path)

#     def _add_demonstration_to_history(self, demonstration_path: Path) -> None:
#         """Load demonstration from disk and add to history"""
#         if self.templates.demonstration_template is None and not self.templates.put_demos_in_history:
#             msg = "Cannot use demonstrations without a demonstration template or put_demos_in_history=True"
#             raise ValueError(msg)

#         # Load history
#         self.logger.info(f"DEMONSTRATION: {demonstration_path}")
#         _demo_text = Path(demonstration_path).read_text()
#         if demonstration_path.suffix == ".yaml":
#             demo_history = yaml.safe_load(_demo_text)["history"]
#         else:
#             demo_history = json.loads(_demo_text)["history"]

#         if self.templates.put_demos_in_history:
#             # Add demonstrations to history step-by-step
#             for entry in demo_history:
#                 if entry["role"] != "system":
#                     entry["is_demo"] = True
#                     self._append_history(entry)
#         else:
#             # Add demonstration as single message to history
#             demo_history = [entry for entry in demo_history if entry["role"] != "system"]
#             demo_message = "\n".join([entry["content"] for entry in demo_history])
#             assert self.templates.demonstration_template is not None
#             demonstration = Template(self.templates.demonstration_template).render(demonstration=demo_message)
#             self._append_history(
#                 {
#                     "agent": self.name,
#                     "content": demonstration,
#                     "is_demo": True,
#                     "role": "user",
#                     "message_type": "demonstration",
#                 },
#             )

#     def _get_format_dict(self, **kwargs) -> dict[str, Any]:
#         """Get the dictionary of key value pairs used to format the templates

#         Args:
#             **kwargs: additional keyword arguments to be added to the format dictionary
#         """
#         assert self._problem_statement is not None
#         assert self._env is not None
#         return dict(
#             command_docs=self.tools.config.command_docs,
#             **self.tools.config.env_variables,
#             **kwargs,
#             problem_statement=self._problem_statement.get_problem_statement(),
#             repo=self._env.repo.repo_name if self._env.repo is not None else "",
#             **self._problem_statement.get_extra_fields(),
#         )

#     def _add_templated_messages_to_history(
#         self, templates: list[str], tool_call_ids: list[str] | None = None, **kwargs: str | int | None
#     ) -> None:
#         """Populate selected template(s) with information (e.g., issue, arguments, state)
#         and add to history.

#         Args:
#             templates: templates to populate and add to history
#             tool_call_ids: tool call ids to be added to the history
#             **kwargs: keyword arguments to be passed to the templates (in addition to the
#                 ones in `self._get_format_dict`)
#         """
#         messages = []

#         format_dict = self._get_format_dict(**kwargs)
#         for template in templates:
#             try:
#                 messages.append(Template(template).render(**format_dict))
#             except KeyError:
#                 self.logger.debug("The following keys are available: %s", format_dict.keys())
#                 raise

#         message = "\n".join(messages)

#         # We disable syntax highlighting here, because some inputs can lead to a complete cross-thread
#         # freeze in the agent. See https://github.com/SWE-agent/SWE-agent/issues/901 .
#         self.logger.info(f"🤖 MODEL INPUT\n{message}", extra={"highlighter": None})
#         history_item: dict[str, Any] = {
#             "role": "user",
#             "content": message,
#             "agent": self.name,
#             "message_type": "observation",
#         }
#         if tool_call_ids:
#             assert len(tool_call_ids) == 1, "This should be ensured by the FunctionCalling parse method"
#             history_item["role"] = "tool"
#             history_item["tool_call_ids"] = tool_call_ids
#         self._append_history(history_item)

#     def add_step_to_history(self, step: StepOutput) -> None:
#         """Adds a step (command that was run and output) to the model history"""
#         self._append_history(
#             {
#                 "role": "assistant",
#                 "content": step.output,
#                 "thought": step.thought,
#                 "action": step.action,
#                 "agent": self.name,
#                 "tool_calls": step.tool_calls,
#                 "message_type": "action",
#                 "thinking_blocks": step.thinking_blocks,
#             },
#         )

#         elided_chars = 0
#         if step.observation.strip() == "":
#             # Show no output template if observation content was empty
#             templates = [self.templates.next_step_no_output_template]
#         elif len(step.observation) > self.templates.max_observation_length:
#             templates = [self.templates.next_step_truncated_observation_template]
#             elided_chars = len(step.observation) - self.templates.max_observation_length
#         else:
#             # Show standard output template if there is observation content
#             templates = [self.templates.next_step_template]
#         self._add_templated_messages_to_history(
#             templates,
#             observation=step.observation,
#             elided_chars=elided_chars,
#             max_observation_length=self.templates.max_observation_length,
#             tool_call_ids=step.tool_call_ids,
#             **step.state,
#         )

#     def add_instance_template_to_history(self, state: dict[str, str]) -> None:
#         """Add observation to history, as well as the instance template or demonstrations if we're
#         at the start of a new attempt.
#         """
#         templates: list[str] = []
#         # Determine observation template based on what prior observation was
#         assert self.history[-1]["role"] == "system" or self.history[-1].get("is_demo", False)
#         # Show instance template if prev. obs. was initial system message
#         templates = [self.templates.instance_template]
#         if self.templates.strategy_template is not None:
#             templates.append(self.templates.strategy_template)

#         self._add_templated_messages_to_history(templates, **state)  # type: ignore

#     def get_trajectory_data(self) -> dict[str, Any]:
#         """Get all data that we save in .traj files."""

#         assert self._env is not None
#         # The deepcopy here is important because else the
#         # data["info"]["model_stats"] update will create havoc!
#         attempt_data = copy.deepcopy(
#             {
#                 "trajectory": self.trajectory,
#                 "history": self.history,
#                 "info": self.info,
#             }
#         )
#         attempt_data["replay_config"] = self.replay_config.model_dump_json() if self.replay_config is not None else None
#         attempt_data["environment"] = self._env.name
#         return attempt_data

#     def save_trajectory(
#         self,
#     ) -> None:
#         """Save the trajectory to disk.
#         This includes the history, the environment state, and the model stats.
#         """
#         data = self.get_trajectory_data()
#         assert self.traj_path is not None
#         self.traj_path.write_text(json.dumps(data, indent=2))

#     def get_model_requery_history(
#         self, error_template: str, *, output: str, **kwargs: str | int | float | bool | None
#     ) -> list[dict[str, str]]:
#         """Ask the model to correct after a hitting one of the following errors:

#         1. Malformatted output (could not parse action)
#         2. Blocked action (command is on the blocklist)
#         3. Bash command syntax error

#         At the time this function is called, the proposed action and observation are not part of the history
#         yet.

#         This function adds temporary history based on the error template and queries the model.
#         If the model is able to correct itself, the records of the mistakes will not be part of the history
#         (but they are saved in the trajectory).

#         Args:
#             error_template: error template
#             output: model output
#             **kwargs: keyword arguments to be passed to the error template

#         Returns:
#             model output after requery
#         """
#         format_dict = {**kwargs, **self._get_format_dict()}
#         error_template = Template(error_template).render(**format_dict)

#         self.logger.warning(f"{error_template}")

#         return self.messages + [
#             {"role": "assistant", "content": output, "agent": self.name, "message_type": "assistant"},
#             {"role": "user", "content": error_template, "agent": self.name, "message_type": "user"},
#         ]

#     def attempt_autosubmission_after_error(self, step: StepOutput) -> StepOutput:
#         """For most exceptions, we attempt to still extract the patch and submit that.
#         This means we send the `submit` command to the runtime and parse the output.
#         """
#         self.logger.warning("Attempting autosubmission after error")
#         step = step.model_copy(deep=True)
#         step.done = True
#         assert self._env is not None
#         if not asyncio.run(self._env.deployment.is_alive(timeout=10)):
#             # The agent is dead. This is very bad. Maybe we can take a 'diff' that was saved
#             # for a previous step? (if running with diff in tools)
#             self.logger.error("Runtime is no longer alive")
#             try:
#                 last_trajectory_step = self.trajectory[-1]
#             except IndexError:
#                 self.logger.info("No last trajectory step to extract patch from")
#                 return step
#             if "diff" not in last_trajectory_step["state"]:
#                 self.logger.info("No diff in last trajectory step state, cannot autosubmit")
#                 return step
#             diff = last_trajectory_step["state"]["diff"]
#             self.logger.info("Using diff from last trajectory step to autosubmit")
#             step.submission = diff
#             if step.submission:
#                 step.observation = "Environment died unexpectedly. Exited (autosubmitted)"
#                 step.exit_status = f"submitted ({step.exit_status})"
#             else:
#                 self.logger.info("Diff from last traj step empty.")
#             return step
#         # Let us manually run the submission command and collect the output
#         repo_name = "/"
#         if self._env.repo is not None:
#             repo_name = f"/{self._env.repo.repo_name}"
#         submission_command = "git add -A && git diff --cached > /root/model.patch"
#         self.logger.info("Executing submission command %s in %s", submission_command, repo_name)
#         try:
#             self._env.execute_command(submission_command, check=True, cwd=repo_name)
#         except Exception as e:
#             self.logger.error("Failed to execute submission command, got %s", e)
#         # There's still hope for the submission, because the `/root/model.patch` file might have been
#         # generated by the state command
#         step = self.handle_submission(step, observation="", force_submission=True)
#         if step.submission:
#             self.logger.info("Exiting with autosubmission")
#             step.observation = "Exited (autosubmitted)"
#         return step

#     def handle_submission(self, step: StepOutput, *, observation="", force_submission: bool = False) -> StepOutput:
#         """Check if there was a submission in the observation and handle it.

#         Args:
#             step:
#             observation: If specified, will use this rather than stepobservation
#             force_submission: If True, will always submit even if no submission is found

#         Returns:
#             step: step with submission and observation updated (if submission was found)
#         """
#         step = step.model_copy(deep=True)
#         assert self.tools is not None
#         is_submission = self.tools.check_for_submission_cmd(observation or step.observation)
#         if is_submission or force_submission:
#             assert self._env is not None
#             try:
#                 submission = self._env.read_file("/root/model.patch", encoding="utf-8", errors="backslashreplace")
#             except FileNotFoundError:
#                 self.logger.warning("Submission file not found, no submission was made")
#                 return step
#             except Exception as e:
#                 self.logger.exception("Failed to read submission file, got %s", e)
#                 return step
#             if submission.strip() != "":
#                 step.submission = submission
#             else:
#                 step.submission = None
#             step.observation = submission
#             if not step.exit_status:
#                 step.exit_status = "submitted"
#             elif step.submission:
#                 step.exit_status = f"submitted ({step.exit_status})"
#             step.done = True
#             self.logger.info(f"Found submission: {submission}")
#         return step

#     def _get_edited_files_with_context(self, patch: str) -> dict[str, str]:
#         """Get the edited files with context from the patch"""
#         assert self._env is not None
#         try:
#             if self._env.repo is None:
#                 pf = None
#             else:
#                 pf = (
#                     PatchFormatter(
#                         patch,
#                         read_method=lambda path: self._env.read_file(  # type: ignore[attr-defined]
#                             PurePosixPath("/") / self._env.repo.repo_name / path  # type: ignore[attr-defined]
#                         ),
#                     )
#                     if patch
#                     else None
#                 )
#         except UnidiffParseError:
#             self.logger.error("Failed to parse patch with unidiff. Some variables will be empty.")
#             pf = None
#             # We still need to populate the variables
#         out = {}
#         for context_length in [30, 50, 70]:
#             value = "Empty. No edited files found."
#             if pf is not None:
#                 value = pf.get_files_str(original=False, context_length=context_length)
#             out[f"edited_files{context_length}"] = value
#         return out


#     # def handle_action(self, step: StepOutput) -> StepOutput:
#     #     """Runs an action proposed by the agent in the environment."""
#     #     if self.tools.should_block_action(step.action):
#     #         raise _BlockedActionError()

#     #     if step.action.strip() == "exit":
#     #         self.logger.info("Exiting agent")
#     #         step.done = True
#     #         step.observation = "Exited"
#     #         step.exit_status = "exit_command"
#     #         assert self._env is not None
#     #         step.state = self.tools.get_state(env=self._env)
#     #         return step

#     #     assert self._env is not None
#     #     self._chook.on_action_started(step=step)
#     #     execution_t0 = time.perf_counter()
#     #     run_action: str = self.tools.guard_multiline_input(step.action).strip()
        
#     #     # TIMING: Determine command category
#     #     tracker = get_timing_tracker()
#     #     command_parts = run_action.split()
#     #     command_name = command_parts[0] if command_parts else ""
        
#     #     # Truncate command for logging (avoid huge commands in output)
#     #     command_for_log = run_action[:200] + "..." if len(run_action) > 200 else run_action
        
#     #     # Handle str_replace_editor sub-commands
#     #     if command_name == 'str_replace_editor' and len(command_parts) > 1:
#     #         sub_command = command_parts[1]
#     #         if sub_command == 'view':
#     #             timing_category = "file_views"
#     #         elif sub_command in ['str_replace', 'create', 'insert', 'undo_edit']:
#     #             timing_category = "edit_commands"
#     #         else:
#     #             timing_category = "other_tools"
#     #     elif command_name in ['edit', 'create']:
#     #         timing_category = "edit_commands"
#     #     elif command_name in ['open', 'scroll_down', 'scroll_up', 'goto']:
#     #         timing_category = "file_views"
#     #     elif command_name in ['cat', 'head', 'tail', 'less', 'more']:
#     #         timing_category = "file_views"
#     #     elif command_name in ['find_file', 'search_dir', 'search_file', 'grep', 'find', 'ag', 'rg']:
#     #         timing_category = "file_searches"
#     #     elif command_name in ['submit', 'exit', 'exit_forfeit']:
#     #         timing_category = "context_management"
#     #     else:
#     #         timing_category = "shell_commands"
        
#     #     # Start timer with command string
#     #     timer_key = tracker.start_timer(timing_category, command_for_log)
        
#     #     try:
#     #         step.observation = self._env.communicate(
#     #             input=run_action,
#     #             timeout=self.tools.config.execution_timeout,
#     #             check="raise" if self._always_require_zero_exit_code else "ignore",
#     #         )
#     #     except CommandTimeoutError:
#     #         self._n_consecutive_timeouts += 1
#     #         if self._n_consecutive_timeouts >= self.tools.config.max_consecutive_execution_timeouts:
#     #             msg = "Exiting agent due to too many consecutive execution timeouts"
#     #             self.logger.critical(msg)
#     #             step.execution_time = time.perf_counter() - execution_t0
#     #             self._total_execution_time += step.execution_time
#     #             tracker.end_timer(timer_key, timing_category)
#     #             raise
#     #         try:
#     #             self._env.interrupt_session()
#     #         except Exception as f:
#     #             self.logger.exception("Failed to interrupt session after command timeout: %s", f, exc_info=True)
#     #             step.execution_time = time.perf_counter() - execution_t0
#     #             self._total_execution_time += step.execution_time
#     #             tracker.end_timer(timer_key, timing_category)
#     #             raise
#     #         step.observation = Template(self.templates.command_cancelled_timeout_template).render(
#     #             **self._get_format_dict(),
#     #             timeout=self.tools.config.execution_timeout,
#     #             command=run_action,
#     #         )
#     #     else:
#     #         self._n_consecutive_timeouts = 0
#     #     finally:
#     #         # END TIMING for tool execution
#     #         tracker.end_timer(timer_key, timing_category)
            
#     #     step.execution_time = time.perf_counter() - execution_t0
#     #     self._total_execution_time += step.execution_time
#     #     self._chook.on_action_executed(step=step)
#     #     step.state = self.tools.get_state(env=self._env)

#     #     if RETRY_WITH_OUTPUT_TOKEN in step.observation:
#     #         step.observation = step.observation.replace(RETRY_WITH_OUTPUT_TOKEN, "")
#     #         raise _RetryWithOutput()
#     #     elif RETRY_WITHOUT_OUTPUT_TOKEN in step.observation:
#     #         step.observation = step.observation.replace(RETRY_WITHOUT_OUTPUT_TOKEN, "")
#     #         raise _RetryWithoutOutput()
#     #     elif EXIT_FORFEIT_TOKEN in step.observation:
#     #         raise _ExitForfeit()

#     #     return self.handle_submission(step)

#     def handle_action(self, step: StepOutput) -> StepOutput:
#         """Runs an action proposed by the agent in the environment."""
#         if self.tools.should_block_action(step.action):
#             raise _BlockedActionError()

#         if step.action.strip() == "exit":
#             self.logger.info("Exiting agent")
#             step.done = True
#             step.observation = "Exited"
#             step.exit_status = "exit_command"
#             assert self._env is not None
#             # TIMING: state retrieval on exit path
#             tracker = get_timing_tracker()
#             state_timer = tracker.start_timer("state_retrieval", "get_state (exit)")
#             step.state = self.tools.get_state(env=self._env)
#             tracker.end_timer(state_timer, "state_retrieval")
#             return step

#         assert self._env is not None
#         self._chook.on_action_started(step=step)
#         execution_t0 = time.perf_counter()
#         run_action: str = self.tools.guard_multiline_input(step.action).strip()
        
#         # TIMING: Determine command category
#         tracker = get_timing_tracker()
#         command_parts = run_action.split()
#         command_name = command_parts[0] if command_parts else ""
        
#         # Truncate command for logging (avoid huge commands in output)
#         command_for_log = run_action[:200] + "..." if len(run_action) > 200 else run_action
        
#         # Handle str_replace_editor sub-commands
#         if command_name == 'str_replace_editor' and len(command_parts) > 1:
#             sub_command = command_parts[1]
#             if sub_command == 'view':
#                 timing_category = "file_views"
#             elif sub_command in ['str_replace', 'create', 'insert', 'undo_edit']:
#                 timing_category = "edit_commands"
#             else:
#                 timing_category = "other_tools"
#         elif command_name in ['edit', 'create']:
#             timing_category = "edit_commands"
#         elif command_name in ['open', 'scroll_down', 'scroll_up', 'goto']:
#             timing_category = "file_views"
#         elif command_name in ['cat', 'head', 'tail', 'less', 'more']:
#             timing_category = "file_views"
#         elif command_name in ['find_file', 'search_dir', 'search_file', 'grep', 'find', 'ag', 'rg']:
#             timing_category = "file_searches"
#         elif command_name in ['submit', 'exit', 'exit_forfeit']:
#             timing_category = "context_management"
#         else:
#             timing_category = "shell_commands"
        
#         # Start timer for tool execution
#         timer_key = tracker.start_timer(timing_category, command_for_log)
        
#         try:
#             step.observation = self._env.communicate(
#                 input=run_action,
#                 timeout=self.tools.config.execution_timeout,
#                 check="raise" if self._always_require_zero_exit_code else "ignore",
#             )
#         except CommandTimeoutError:
#             self._n_consecutive_timeouts += 1
#             if self._n_consecutive_timeouts >= self.tools.config.max_consecutive_execution_timeouts:
#                 msg = "Exiting agent due to too many consecutive execution timeouts"
#                 self.logger.critical(msg)
#                 step.execution_time = time.perf_counter() - execution_t0
#                 self._total_execution_time += step.execution_time
#                 raise
#             try:
#                 self._env.interrupt_session()
#             except Exception as f:
#                 self.logger.exception("Failed to interrupt session after command timeout: %s", f, exc_info=True)
#                 step.execution_time = time.perf_counter() - execution_t0
#                 self._total_execution_time += step.execution_time
#                 raise
#             step.observation = Template(self.templates.command_cancelled_timeout_template).render(
#                 **self._get_format_dict(),
#                 timeout=self.tools.config.execution_timeout,
#                 command=run_action,
#             )
#         else:
#             self._n_consecutive_timeouts = 0
#         finally:
#             # END TIMING for tool execution (single point — no redundant calls)
#             tracker.end_timer(timer_key, timing_category)
            
#         step.execution_time = time.perf_counter() - execution_t0
#         self._total_execution_time += step.execution_time
#         self._chook.on_action_executed(step=step)

#         # TIMING: state retrieval after action
#         state_timer = tracker.start_timer("state_retrieval", "get_state (post-action)")
#         step.state = self.tools.get_state(env=self._env)
#         tracker.end_timer(state_timer, "state_retrieval")

#         if RETRY_WITH_OUTPUT_TOKEN in step.observation:
#             step.observation = step.observation.replace(RETRY_WITH_OUTPUT_TOKEN, "")
#             raise _RetryWithOutput()
#         elif RETRY_WITHOUT_OUTPUT_TOKEN in step.observation:
#             step.observation = step.observation.replace(RETRY_WITHOUT_OUTPUT_TOKEN, "")
#             raise _RetryWithoutOutput()
#         elif EXIT_FORFEIT_TOKEN in step.observation:
#             raise _ExitForfeit()

#         return self.handle_submission(step)

   
#     def forward(self, history: list[dict[str, str]]) -> StepOutput:
#         """Forward the model without handling errors."""
#         if self._total_execution_time > self.tools.config.total_execution_timeout:
#             raise _TotalExecutionTimeExceeded()

#         step = StepOutput()
#         step.query = copy.deepcopy(history)
#         try:
#             self._chook.on_model_query(messages=history, agent=self.name)
            
#             # START TIMING: LLM inference (with context info)
#             tracker = get_timing_tracker()
#             llm_command_info = f"LLM call (history_len={len(history)}, model={self.model.name if hasattr(self.model, 'name') else 'unknown'})"
#             timer_key = tracker.start_timer("llm_inference", llm_command_info)
            
#             try:
#                 if self._action_sampler is not None:
#                     assert self._problem_statement is not None
#                     best = self._action_sampler.get_action(
#                         problem_statement=self._problem_statement,
#                         trajectory=self.trajectory,
#                         history=history,
#                     )
#                     output = best.completion
#                     step.extra_info.update(best.extra_info)
#                 else:
#                     output = self.model.query(history)
#             finally:
#                 # END TIMING: LLM inference
#                 tracker.end_timer(timer_key, "llm_inference")
            
#             step.output = output["message"]
#             step.thought, step.action = self.tools.parse_actions(output)
#             step.thinking_blocks = output.get("thinking_blocks", [])
#             if output.get("tool_calls") is not None:
#                 step.tool_call_ids = [call["id"] for call in output["tool_calls"]]
#                 step.tool_calls = output["tool_calls"]
#             self.logger.info(f"💭 THOUGHT\n{step.thought}\n\n🎬 ACTION\n{step.action.strip()}")
#             self._chook.on_actions_generated(step=step)
#             return self.handle_action(step)
#         except Exception as e:
#             if step.action == step.thought == "":
#                 step.thought = step.output
#             e.step = step  # type: ignore
#             raise

#     def forward_with_handling(self, history: list[dict[str, str]]) -> StepOutput:
#         """Forward the model and handle errors, requerying the model if we can.
#         For example, if the model outputs a bash command that has syntax errors,
#         we will not execute it but requery the model for a corrected command.

#         Note: This will update the trajectory, but not the history.

#         Args:
#             history: history to forward

#         Returns:
#             step_output: step output
#         """

#         def handle_error_with_autosubmission(exit_status: str, message: str) -> StepOutput:
#             """Attempts to autosubmit (extract patch from the environment) and stops the loop."""
#             self.logger.warning(message)
#             return self.attempt_autosubmission_after_error(
#                 StepOutput(
#                     thought=message,
#                     exit_status=exit_status,
#                     output=message,
#                     done=True,
#                 )
#             )

#         def handle_error_with_retry(exception: Exception, template: str, n_requeries: int) -> list[dict[str, str]]:
#             """Requeries the model if the error is a format/blocklist/bash syntax error."""
#             self.logger.warning("Requerying model after %s (%dth requery)", type(exception).__name__, n_requeries)
#             step: StepOutput = getattr(exception, "step", StepOutput())
#             self.add_step_to_trajectory(step)
#             exception_message = getattr(exception, "message", "")
#             if not exception_message:
#                 try:
#                     exception_message = exception.args[0]
#                 except (IndexError, AttributeError):
#                     pass
#             return self.get_model_requery_history(
#                 error_template=template,
#                 **step.to_template_format_dict(),
#                 **getattr(exception, "extra_info", {}),
#                 exception_message=exception_message,
#             )

#         n_format_fails = 0
#         while n_format_fails < self.max_requeries:
#             try:
#                 return self.forward(history)

#             # Errors that are raised

#             except KeyboardInterrupt:
#                 raise
#             except EOFError:
#                 raise

#             # Errors that cause requery

#             except FormatError as e:
#                 n_format_fails += 1
#                 history = handle_error_with_retry(
#                     exception=e, template=self.tools.config.format_error_template, n_requeries=n_format_fails
#                 )
#             except _BlockedActionError as e:
#                 n_format_fails += 1
#                 history = handle_error_with_retry(
#                     exception=e, template=self.tools.config.filter.blocklist_error_template, n_requeries=n_format_fails
#                 )
#             except ContentPolicyViolationError:
#                 self.logger.warning("Content policy violation, trying to resample")
#                 n_format_fails += 1
#                 # Try if simply resampling helps here
#                 pass
#             except BashIncorrectSyntaxError as e:
#                 n_format_fails += 1
#                 history = handle_error_with_retry(
#                     exception=e,
#                     template=self.templates.shell_check_error_template,
#                     n_requeries=n_format_fails,
#                 )
#             except _RetryWithOutput as e:
#                 history = handle_error_with_retry(
#                     exception=e,
#                     template=self.templates.next_step_template,
#                     n_requeries=n_format_fails,
#                 )
#             except _RetryWithoutOutput:
#                 pass
#                 # Requery with the same template as the last step

#             # Errors that cause exit

#             except _ExitForfeit:
#                 self.logger.info("Exiting due to forfeit")
#                 return handle_error_with_autosubmission(
#                     "exit_forfeit",
#                     "Exiting due to forfeit",
#                 )

#             except _TotalExecutionTimeExceeded:
#                 self.logger.exception("Exiting due to total execution time exceeded", exc_info=True)
#                 return handle_error_with_autosubmission(
#                     "exit_total_execution_time",
#                     "Exit due to total execution time exceeded",
#                 )

#             except CommandTimeoutError:
#                 self.logger.exception("Exiting due to multiple consecutive command timeouts", exc_info=True)
#                 return handle_error_with_autosubmission(
#                     "exit_command_timeout",
#                     "Exit due to multiple consecutive command timeouts",
#                 )

#             except ContextWindowExceededError:
#                 return handle_error_with_autosubmission(
#                     "exit_context",
#                     "Exit due to context window",
#                 )
#             except TotalCostLimitExceededError:
#                 raise
#             except CostLimitExceededError:
#                 return handle_error_with_autosubmission(
#                     "exit_cost",
#                     "Exit due to cost limit",
#                 )
#             except RetryError as e:
#                 self.logger.exception(f"Exiting due to retry error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission(
#                     "exit_api",
#                     f"Exit due to retry error: {e}",
#                 )
#             except SwerexException as e:
#                 self.logger.exception(f"Exiting due to environment error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission(
#                     "exit_environment_error",
#                     f"Exit due to environment error: {e}",
#                 )
#             except RuntimeError as e:
#                 self.logger.exception(f"Exiting due to runtime error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission(
#                     "exit_error",
#                     f"Exit due to runtime error: {e}",
#                 )
#             except Exception as e:
#                 self.logger.exception(f"Exiting due to unknown error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission(
#                     "exit_error",
#                     f"Exit due to unknown error: {e}",
#                 )
#         self.logger.exception(
#             "Exit due to repeated format/blocklist/bash syntax errors",
#             exc_info=True,
#         )
#         return handle_error_with_autosubmission(
#             "exit_format",
#             "Exit due to repeated format/blocklist/bash syntax errors",
#         )

#     def add_step_to_trajectory(self, step: StepOutput) -> None:
#         trajectory_step = TrajectoryStep(
#             {
#                 "action": step.action,
#                 "observation": step.observation,
#                 "response": step.output,
#                 "thought": step.thought,
#                 "execution_time": step.execution_time,
#                 "state": step.state,
#                 "query": step.query,
#                 "extra_info": step.extra_info,
#             },
#         )
#         self.trajectory.append(trajectory_step)

#     def step(self) -> StepOutput:
#         """Run a step of the agent. This is a wrapper around `self.forward_with_handling`
#         with additional bookkeeping:

#         1. Update message history with performed action and observation
#         2. Update trajectory with the final executed result
#         3. Update the info dictionary

#         Returns:
#             step_output: step output (same as the output of `self.forward_with_handling`)
#         """

#         assert self._env is not None
#         self._chook.on_step_start()

#         n_step = len(self.trajectory) + 1
#         self.logger.info("=" * 25 + f" STEP {n_step} " + "=" * 25)
#         step_output = self.forward_with_handling(self.messages)
#         self.add_step_to_history(step_output)

#         self.info["submission"] = step_output.submission
#         self.info["exit_status"] = step_output.exit_status  # type: ignore
#         self.info.update(self._get_edited_files_with_context(patch=step_output.submission or ""))  # type: ignore
#         self.info["model_stats"] = self.model.stats.model_dump()

#         self.add_step_to_trajectory(step_output)

#         self._chook.on_step_done(step=step_output, info=self.info)
#         return step_output

#     def run(
#         self,
#         env: SWEEnv,
#         problem_statement: ProblemStatement | ProblemStatementConfig,
#         output_dir: Path = Path("."),
#     ) -> AgentRunResult:
#         """Run the agent on a problem instance. This method contains the
#         main loop that repeatedly calls `self._step` until the problem is solved.

#         Args:
#             setup_args: Arguments to pass to the agent's setup method.
#             env: The environment to run the agent on.
#             traj_dir: Directory to save the trajectory to
#         """
#         self.setup(env=env, problem_statement=problem_statement, output_dir=output_dir)

#         # Run action/observation loop
#         self._chook.on_run_start()
#         step_output = StepOutput()
#         while not step_output.done:
#             step_output = self.step()
#             self.save_trajectory()
#         self._chook.on_run_done(trajectory=self.trajectory, info=self.info)

#         self.logger.info("Trajectory saved to %s", self.traj_path)

#         # Here we want to return the "global" information (e.g., submission should
#         # be the best submission instead of the last one, etc.), so we get it from the traj file
#         data = self.get_trajectory_data()
#         return AgentRunResult(info=data["info"], trajectory=data["trajectory"])


















# from __future__ import annotations

# import asyncio
# import copy
# import json
# from sweagent.timing_tracker import get_timing_tracker
# from sweagent.detailed_timing_tracker import get_detailed_timing_tracker, TEST_COMMAND_PATTERNS, GIT_COMMAND_PATTERNS

# import logging
# import time
# from pathlib import Path, PurePosixPath
# from typing import Annotated, Any, Literal

# import yaml
# from jinja2 import Template
# from pydantic import BaseModel, ConfigDict, Field, model_validator
# from simple_parsing.helpers.fields import field
# from swerex.exceptions import BashIncorrectSyntaxError, CommandTimeoutError, SwerexException
# from tenacity import RetryError
# from typing_extensions import Self
# from unidiff import UnidiffParseError

# from sweagent import __version__, get_agent_commit_hash, get_rex_commit_hash, get_rex_version
# from sweagent.agent.action_sampler import AbstractActionSampler, ActionSamplerConfig
# from sweagent.agent.history_processors import DefaultHistoryProcessor, HistoryProcessor
# from sweagent.agent.hooks.abstract import AbstractAgentHook, CombinedAgentHook
# from sweagent.agent.models import (
#     AbstractModel,
#     HumanModel,
#     HumanThoughtModel,
#     InstanceStats,
#     ModelConfig,
#     get_model,
# )
# from sweagent.agent.problem_statement import ProblemStatement, ProblemStatementConfig
# from sweagent.agent.reviewer import (
#     ChooserRetryLoop,
#     RetryLoopConfig,
#     ReviewSubmission,
#     ScoreRetryLoop,
#     get_retry_loop_from_config,
# )
# from sweagent.environment.swe_env import SWEEnv
# from sweagent.exceptions import (
#     ContentPolicyViolationError,
#     ContextWindowExceededError,
#     CostLimitExceededError,
#     FormatError,
#     TotalCostLimitExceededError,
# )
# from sweagent.tools.parsing import (
#     ActionOnlyParser,
#     ThoughtActionParser,
# )
# from sweagent.tools.tools import ToolConfig, ToolHandler
# from sweagent.types import AgentInfo, AgentRunResult, StepOutput, Trajectory, TrajectoryStep
# from sweagent.utils.config import _convert_paths_to_abspath, _strip_abspath_from_dict
# from sweagent.utils.jinja_warnings import _warn_probably_wrong_jinja_syntax
# from sweagent.utils.log import get_logger
# from sweagent.utils.patch_formatter import PatchFormatter


# # ── helper: classify a command for the detailed tracker ──────────────
# def _classify_command_detailed(run_action: str) -> str:
#     """Return the *detailed* timing category for an action string."""
#     parts = run_action.split()
#     cmd = parts[0] if parts else ""

#     # Test / validation
#     action_lower = run_action.lower()
#     for pat in TEST_COMMAND_PATTERNS:
#         if action_lower.startswith(pat):
#             return "test_validation_execution"

#     # Git operations (submit handled separately by the caller)
#     for pat in GIT_COMMAND_PATTERNS:
#         if action_lower.startswith(pat):
#             return "git_operations"

#     # str_replace_editor sub-commands
#     if cmd == "str_replace_editor" and len(parts) > 1:
#         sub = parts[1]
#         if sub == "view":
#             return "repository_scan"
#         elif sub == "create":
#             return "file_creation"
#         elif sub in ("str_replace", "insert", "undo_edit"):
#             return "apply_file_changes"
#         return "shell_command_execution"

#     if cmd == "create":
#         return "file_creation"
#     if cmd in ("edit",):
#         return "apply_file_changes"
#     if cmd in ("open", "scroll_down", "scroll_up", "goto", "cat", "head", "tail", "less", "more"):
#         return "repository_scan"
#     if cmd in ("find_file", "search_dir", "search_file", "grep", "find", "ag", "rg"):
#         return "repository_scan"
#     if cmd in ("submit",):
#         return "git_operations"

#     return "shell_command_execution"


# # ── helper: classify a command for the original tracker ──────────────
# def _classify_command_original(run_action: str) -> str:
#     """Return the *original* timing category for an action string."""
#     parts = run_action.split()
#     cmd = parts[0] if parts else ""

#     if cmd == "str_replace_editor" and len(parts) > 1:
#         sub = parts[1]
#         if sub == "view":
#             return "file_views"
#         elif sub in ("str_replace", "create", "insert", "undo_edit"):
#             return "edit_commands"
#         return "other_tools"
#     if cmd in ("edit", "create"):
#         return "edit_commands"
#     if cmd in ("open", "scroll_down", "scroll_up", "goto", "cat", "head", "tail", "less", "more"):
#         return "file_views"
#     if cmd in ("find_file", "search_dir", "search_file", "grep", "find", "ag", "rg"):
#         return "file_searches"
#     if cmd in ("submit", "exit", "exit_forfeit"):
#         return "context_management"
#     return "shell_commands"


# class TemplateConfig(BaseModel):
#     """This configuration is used to define almost all message templates that are
#     formatted by the agent and sent to the LM.
#     """

#     system_template: str = ""
#     instance_template: str = ""
#     next_step_template: str = "Observation: {{observation}}"

#     next_step_truncated_observation_template: str = (
#         "Observation: {{observation[:max_observation_length]}}<response clipped>"
#         "<NOTE>Observations should not exceeded {{max_observation_length}} characters. "
#         "{{elided_chars}} characters were elided. Please try a different command that produces less output "
#         "or use head/tail/grep/redirect the output to a file. Do not use interactive pagers.</NOTE>"
#     )
#     """Message template for when the agent's observation was truncated.
#     Available variables: `observation`, `max_observation_length`, `elided_chars`
#     """

#     max_observation_length: int = 100_000
#     """Truncate observation to this length if it exceeds it.
#     This in measured in characters, i.e., as `len(observation)`.
#     """

#     next_step_no_output_template: str = None  # type: ignore
#     """Template for the next step when the last output was empty. Defaults to next_step_template."""

#     strategy_template: str | None = None
#     demonstration_template: str | None = None

#     demonstrations: list[Path] = field(default_factory=list)
#     """Paths to demonstrations. If path is not absolute, it is assumed to be
#     relative to the SWE_AGENT_CONFIG_ROOT (if set) or the SWE-agent repository root
#     """

#     put_demos_in_history: bool = False
#     """If True, add demonstration to history instead of as a single message"""

#     disable_image_processing: bool = False
#     """If True, disable image processing for multimodal problem statements (i.e. SWEBenchMultimodalProblemStatement).
#     """

#     shell_check_error_template: str = (
#         "Your bash command contained syntax errors and was NOT executed. "
#         "Please fix the syntax errors and try again. This can be the result "
#         "of not adhering to the syntax for multi-line commands. Here is the output of `bash -n`:\n"
#         "{{bash_stdout}}\n{{bash_stderr}}"
#     )
#     """Message template for when the agent's bash command contains syntax errors.
#     Available variables: `bash_stdout`, `bash_stderr`
#     """

#     command_cancelled_timeout_template: str = (
#         "The command '{{command}}' was cancelled because it took more than {{timeout}} seconds. "
#         "Please try a different command that completes more quickly. "
#         "Note: A common source of this error is if the command is interactive or requires user input "
#         "(it is impossible to receive user input in the current environment, so the command will never complete)."
#     )
#     """Message template for when the agent's command was cancelled because it took too long.
#     Available variables: `timeout`, `command`
#     """

#     def model_post_init(self, __context):
#         self.demonstrations = _convert_paths_to_abspath(self.demonstrations)
#         if self.next_step_no_output_template is None:
#             self.next_step_no_output_template = self.next_step_template

#     @model_validator(mode="after")
#     def validate_template_jinja_syntax(self) -> Self:
#         template_fields = [field for field in self.model_fields.keys() if field.endswith("_template")]
#         for field in template_fields:
#             value = getattr(self, field)
#             _warn_probably_wrong_jinja_syntax(value)
#         return self

#     @model_validator(mode="after")
#     def warnings(self) -> Self:
#         logger = get_logger("swea-config", emoji="🔧")
#         if self.put_demos_in_history and self.demonstration_template is not None:
#             logger.warning("demonstration_template is ignored when put_demos_in_history is True")
#         if not self.system_template or not self.instance_template:
#             logger.warning(
#                 "system_template/instance_template is not set, using empty string. Perhaps you were"
#                 " overwriting the default config? See https://swe-agent.com/latest/usage/cl_tutorial/"
#                 " for more information. Note: You can ignore this warning in human mode."
#             )
#         return self


# class DefaultAgentConfig(BaseModel):
#     """This configuration object specifies the behavior of an agent."""

#     name: str = "main"
#     templates: TemplateConfig = Field(default_factory=TemplateConfig)
#     tools: ToolConfig = Field(default_factory=ToolConfig)
#     history_processors: list[HistoryProcessor] = Field(default_factory=lambda: [DefaultHistoryProcessor()])
#     model: ModelConfig = Field(description="Model options.")

#     max_requeries: int = 3
#     """Maximum number of times to requery the model after an error, such as a
#     formatting error, a blocked action, or a bash syntax error.
#     """
#     action_sampler: ActionSamplerConfig | None = None

#     type: Literal["default"] = "default"

#     # pydantic config
#     model_config = ConfigDict(extra="forbid")


# class ShellAgentConfig(BaseModel):
#     name: str = "main"
#     templates: TemplateConfig = Field(default_factory=TemplateConfig)
#     tools: ToolConfig = Field(default_factory=ToolConfig)
#     history_processors: list[HistoryProcessor] = Field(default_factory=lambda: [DefaultHistoryProcessor()])
#     model: ModelConfig = Field(description="Model options.")

#     max_requeries: int = 3
#     """Maximum number of times to requery the model after an error, such as a
#     formatting error, a blocked action, or a bash syntax error.
#     """

#     type: Literal["shell"] = "shell"

#     # pydantic config
#     model_config = ConfigDict(extra="forbid")


# class RetryAgentConfig(BaseModel):
#     name: str = "retry_main"
#     agent_configs: list[DefaultAgentConfig]
#     retry_loop: RetryLoopConfig
#     type: Literal["retry"] = "retry"
#     model_config = ConfigDict(extra="forbid")


# AgentConfig = Annotated[DefaultAgentConfig | RetryAgentConfig | ShellAgentConfig, Field(union_mode="left_to_right")]


# class _BlockedActionError(Exception):
#     """Raised when the agent's action is blocked"""


# class _RetryWithOutput(Exception):
#     """Used for internal control flow"""


# class _RetryWithoutOutput(Exception):
#     """Used for internal control flow"""


# class _ExitForfeit(Exception):
#     """Used for internal control flow"""


# class _TotalExecutionTimeExceeded(Exception):
#     """Used for internal control flow"""


# RETRY_WITH_OUTPUT_TOKEN = "###SWE-AGENT-RETRY-WITH-OUTPUT###"
# RETRY_WITHOUT_OUTPUT_TOKEN = "###SWE-AGENT-RETRY-WITHOUT-OUTPUT###"
# EXIT_FORFEIT_TOKEN = "###SWE-AGENT-EXIT-FORFEIT###"


# class AbstractAgent:
#     def __init__(self, *args, **kwargs):
#         model: AbstractModel
#         replay_config: BaseModel | None
#         logger: logging.Logger

#     @classmethod
#     def from_config(cls, config: AgentConfig) -> Self: ...

#     def add_hook(self, hook: AbstractAgentHook) -> None: ...

#     def get_trajectory_data(self) -> dict[str, Any]: ...

#     def step(self) -> StepOutput: ...

#     def run(self, *args, **kwargs) -> AgentRunResult: ...


# def get_agent_from_config(config: AgentConfig) -> AbstractAgent:
#     if config.type == "default":
#         return DefaultAgent.from_config(config)
#     elif config.type == "retry":
#         return RetryAgent.from_config(config)
#     elif config.type == "shell":
#         from sweagent.agent.extra.shell_agent import ShellAgent

#         return ShellAgent.from_config(config)
#     else:
#         msg = f"Unknown agent type: {config.type}"
#         raise ValueError(msg)


# class RetryAgent(AbstractAgent):
#     def __init__(self, config: RetryAgentConfig):
#         self.config = config.model_copy(deep=True)
#         self._hooks = []
#         self._i_attempt = 0
#         self.logger = get_logger("swea-agent", emoji="🤠")
#         self._agent: DefaultAgent | None = None
#         self._attempt_data: list[dict[str, Any]] = []
#         self._total_instance_attempt_stats = InstanceStats()
#         self._chook = CombinedAgentHook()
#         self._traj_path: Path | None = None
#         self._problem_statement: ProblemStatement | None = None
#         self._env: SWEEnv | None = None
#         self._output_dir: Path | None = None
#         self._rloop: ScoreRetryLoop | ChooserRetryLoop | None = None

#     @property
#     def _total_instance_stats(self) -> InstanceStats:
#         assert self._rloop is not None
#         return self._total_instance_attempt_stats + self._rloop.review_model_stats

#     @classmethod
#     def from_config(cls, config: RetryAgentConfig) -> Self:
#         return cls(config)

#     def add_hook(self, hook: AbstractAgentHook) -> None:
#         self._chook.add_hook(hook)
#         self._hooks.append(hook)

#     def setup(
#         self, env: SWEEnv, problem_statement: ProblemStatement | ProblemStatementConfig, output_dir: Path = Path(".")
#     ) -> None:
#         self._total_instance_attempt_stats = InstanceStats()
#         self._problem_statement = problem_statement
#         self._traj_path = output_dir / (self._problem_statement.id + ".traj")
#         self._env = env
#         self._output_dir = output_dir
#         self._rloop = get_retry_loop_from_config(self.config.retry_loop, problem_statement=problem_statement)

#     def _setup_agent(self) -> AbstractAgent:
#         agent_config = self.config.agent_configs[self._i_attempt % len(self.config.agent_configs)].model_copy(deep=True)
#         remaining_budget = self.config.retry_loop.cost_limit - self._total_instance_stats.instance_cost
#         if remaining_budget < agent_config.model.per_instance_cost_limit:
#             self.logger.debug("Setting agent per-attempt cost limit to remaining budget: %s", remaining_budget)
#             agent_config.model.per_instance_cost_limit = remaining_budget
#         self._agent = DefaultAgent.from_config(agent_config)
#         for hook in self._hooks:
#             self._agent.add_hook(hook)
#         assert self._output_dir is not None
#         sub_agent_output_dir = self._output_dir / f"attempt_{self._i_attempt}"
#         assert self._problem_statement is not None
#         assert self._env is not None
#         self._agent.setup(env=self._env, problem_statement=self._problem_statement, output_dir=sub_agent_output_dir)
#         return self._agent

#     def _next_attempt(self) -> None:
#         assert self._env is not None
#         self._i_attempt += 1
#         self._env.hard_reset()
#         self._setup_agent()

#     def step(self) -> StepOutput:
#         assert self._agent is not None
#         if self._total_instance_stats.instance_cost > 1.1 * self.config.retry_loop.cost_limit > 0:
#             msg = "Total instance cost exceeded cost limit. This should not happen, please report this. Triggering autosubmit."
#             self.logger.critical(msg)
#             return self._agent.attempt_autosubmission_after_error(step=StepOutput())
#         try:
#             step = self._agent.step()
#         except TotalCostLimitExceededError:
#             raise
#         except Exception as e:
#             msg = "Error in agent step: %s. This really shouldn't happen, please report this. Triggering autosubmit."
#             self.logger.critical(msg, e, exc_info=True)
#             step = self._agent.attempt_autosubmission_after_error(step=StepOutput())
#         return step

#     def _finalize_agent_run(self) -> None:
#         assert self._agent is not None
#         self._agent.save_trajectory()
#         self._attempt_data.append(self._agent.get_trajectory_data())
#         self._total_instance_attempt_stats += self._agent.model.stats

#     def get_trajectory_data(self, choose: bool) -> dict[str, Any]:
#         assert self._rloop is not None
#         data = {"attempts": self._attempt_data}
#         if choose:
#             try:
#                 best_attempt_idx = self._rloop.get_best()
#             except TotalCostLimitExceededError:
#                 raise
#             except Exception as e:
#                 self.logger.critical(f"Error getting best attempt index: {e}. Setting to 0.", exc_info=True)
#                 best_attempt_idx = 0
#             data |= copy.deepcopy(self._attempt_data[best_attempt_idx])
#             data["info"]["best_attempt_idx"] = best_attempt_idx
#             data["info"]["rloop_model_stats"] = self._rloop.review_model_stats.model_dump()
#             data["info"]["model_stats"] = self._total_instance_stats.model_dump()
#             if isinstance(self._rloop, ChooserRetryLoop):
#                 data["info"]["chooser"] = (
#                     self._rloop._chooser_output.model_dump() if self._rloop._chooser_output else {}
#                 )
#         return data

#     def save_trajectory(self, choose: bool) -> None:
#         data = self.get_trajectory_data(choose=choose)
#         assert self._traj_path is not None
#         self._traj_path.write_text(json.dumps(data, indent=2))

#     def run(
#         self,
#         env: SWEEnv,
#         problem_statement: ProblemStatement | ProblemStatementConfig,
#         output_dir: Path = Path("."),
#     ) -> AgentRunResult:
#         output_dir.mkdir(parents=True, exist_ok=True)
#         self.setup(env=env, problem_statement=problem_statement, output_dir=output_dir)
#         assert self._rloop is not None
#         self._chook.on_run_start()
#         step_output = StepOutput()
#         self._setup_agent()
#         assert self._agent is not None
#         while not step_output.done:
#             step_output = self.step()
#             self.save_trajectory(choose=False)
#             if step_output.done:
#                 self._rloop.on_submit(
#                     ReviewSubmission(
#                         trajectory=self._agent.trajectory,
#                         info=self._agent.info,
#                         model_stats=self._agent.model.stats,
#                     )
#                 )
#                 if isinstance(self._rloop, ScoreRetryLoop):
#                     self._agent.info["review"] = self._rloop.reviews[-1].model_dump()
#                 self._finalize_agent_run()
#                 self.save_trajectory(choose=False)
#                 if self._rloop.retry():
#                     assert self._env is not None
#                     self._next_attempt()
#                     step_output.done = False
#         self.save_trajectory(choose=True)
#         self._chook.on_run_done(trajectory=self._agent.trajectory, info=self._agent.info)
#         self.logger.info("Trajectory saved to %s", self._traj_path)
#         data = self.get_trajectory_data(choose=True)
#         return AgentRunResult(info=data["info"], trajectory=data["trajectory"])


# class DefaultAgent(AbstractAgent):
#     def __init__(
#         self,
#         *,
#         templates: TemplateConfig,
#         tools: ToolHandler,
#         history_processors: list[HistoryProcessor],
#         model: AbstractModel,
#         max_requeries: int = 3,
#         name: str = "main",
#         _catch_errors: bool = True,
#         _always_require_zero_exit_code: bool = False,
#         action_sampler_config: ActionSamplerConfig | None = None,
#     ):
#         self._catch_errors = _catch_errors
#         self._always_require_zero_exit_code = _always_require_zero_exit_code
#         self.name = name
#         self.model = model
#         self.templates = templates
#         self.tools = tools
#         if isinstance(self.model, HumanThoughtModel):
#             self.tools.config.parse_function = ThoughtActionParser()
#         elif isinstance(self.model, HumanModel):
#             self.tools.config.parse_function = ActionOnlyParser()
#         self.history_processors = history_processors
#         self.max_requeries = max_requeries
#         self.logger = get_logger("swea-agent", emoji="🤠")
#         self._env: SWEEnv | None = None
#         self._problem_statement: ProblemStatement | ProblemStatementConfig | None = None
#         self.traj_path: Path | None = None
#         self.history = []
#         self._trajectory = []
#         self.info = AgentInfo()
#         self._chook = CombinedAgentHook()
#         self._replay_config: BaseModel | None = None
#         self._action_sampler: AbstractActionSampler | None = None
#         if action_sampler_config is not None:
#             self._action_sampler = action_sampler_config.get(self.model, self.tools)
#         self._n_consecutive_timeouts = 0
#         self._total_execution_time = 0.0

#     @classmethod
#     def from_config(cls, config: DefaultAgentConfig) -> Self:
#         config = config.model_copy(deep=True)
#         model = get_model(config.model, config.tools)
#         return cls(
#             templates=config.templates,
#             tools=ToolHandler(config.tools),
#             history_processors=config.history_processors,
#             model=model,
#             max_requeries=config.max_requeries,
#             action_sampler_config=config.action_sampler,
#         )

#     def add_hook(self, hook: AbstractAgentHook) -> None:
#         hook.on_init(agent=self)
#         self._chook.add_hook(hook)

#     @property
#     def trajectory(self) -> Trajectory:
#         return self._trajectory

#     @property
#     def replay_config(self) -> BaseModel | None:
#         return self._replay_config

#     @replay_config.setter
#     def replay_config(self, value: BaseModel):
#         from sweagent.run.run_single import RunSingleConfig
#         self._replay_config = RunSingleConfig.model_validate(_strip_abspath_from_dict(value.model_dump()))

#     @property
#     def messages(self) -> list[dict[str, Any]]:
#         """Return the history of the agent for this attempt since the last reset,
#         processed through all history processors.
#         """
#         # TIMING: context compaction
#         detailed = get_detailed_timing_tracker()
#         cc_key = detailed.start_entry("context_compaction", detail="history processor chain")

#         filtered_history = [entry for entry in self.history if entry["agent"] == self.name]
#         messages = filtered_history
#         for processor in self.history_processors:
#             messages = processor(messages)

#         detailed.end_entry(cc_key, "context_compaction")
#         return messages

#     # Methods
#     # -------

#     def _append_history(self, item: dict[str, Any]) -> None:
#         self._chook.on_query_message_added(**item)
#         self.history.append(item)

#     def setup(
#         self,
#         env: SWEEnv,
#         problem_statement: ProblemStatement | ProblemStatementConfig,
#         output_dir: Path = Path("."),
#     ) -> None:
#         output_dir.mkdir(parents=True, exist_ok=True)

#         # TIMING: original tracker - agent setup
#         tracker = get_timing_tracker()
#         setup_timer_key = tracker.start_timer("agent_setup", "agent.setup()")

#         # TIMING: detailed tracker - prompt construction (covers template rendering in setup)
#         detailed = get_detailed_timing_tracker()
#         prompt_key = detailed.start_entry("prompt_construction", detail="agent.setup() - system/instance prompt construction")

#         try:
#             if hasattr(problem_statement, "type") and problem_statement.type == "swe_bench_multimodal":
#                 from sweagent.agent.problem_statement import SWEBenchMultimodalProblemStatement
#                 if isinstance(problem_statement, SWEBenchMultimodalProblemStatement):
#                     if not problem_statement.disable_image_processing and self.templates.disable_image_processing:
#                         problem_statement.disable_image_processing = True

#             self._problem_statement = problem_statement
#             self._env = env
#             iid = self._problem_statement.id
#             self.logger.info("Setting up agent for instance %s", iid)

#             self.traj_path = output_dir / (self._problem_statement.id + ".traj")
#             self.logger.info("Trajectory will be saved to %s", self.traj_path)

#             self._chook.on_tools_installation_started()
#             self.tools.install(self._env)
#             self._chook.on_setup_attempt()
#             self.info = AgentInfo()
#             self.info["swe_agent_hash"] = get_agent_commit_hash()
#             self.info["swe_agent_version"] = __version__
#             self.info["swe_rex_version"] = get_rex_version()
#             self.info["swe_rex_hash"] = get_rex_commit_hash()
#             assert self._env is not None
#             assert self._problem_statement is not None
#             self._env.set_env_variables({"PROBLEM_STATEMENT": self._problem_statement.get_problem_statement_for_env()})
#             self.add_system_message_to_history()
#             self.add_demonstrations_to_history()
#             self.add_instance_template_to_history(state=self.tools.get_state(self._env))
#             self._chook.on_setup_done()
#         finally:
#             tracker.end_timer(setup_timer_key, "agent_setup")
#             detailed.end_entry(prompt_key, "prompt_construction")

#     def add_system_message_to_history(self) -> None:
#         assert self._problem_statement is not None
#         system_msg = Template(self.templates.system_template).render(**self._get_format_dict())
#         self.logger.info(f"SYSTEM ({self.name})\n{system_msg}")
#         self._append_history(
#             {"role": "system", "content": system_msg, "agent": self.name, "message_type": "system_prompt"}
#         )

#     def add_demonstrations_to_history(self) -> None:
#         for demonstration_path in self.templates.demonstrations:
#             self._add_demonstration_to_history(demonstration_path)

#     def _add_demonstration_to_history(self, demonstration_path: Path) -> None:
#         if self.templates.demonstration_template is None and not self.templates.put_demos_in_history:
#             msg = "Cannot use demonstrations without a demonstration template or put_demos_in_history=True"
#             raise ValueError(msg)
#         self.logger.info(f"DEMONSTRATION: {demonstration_path}")
#         _demo_text = Path(demonstration_path).read_text()
#         if demonstration_path.suffix == ".yaml":
#             demo_history = yaml.safe_load(_demo_text)["history"]
#         else:
#             demo_history = json.loads(_demo_text)["history"]
#         if self.templates.put_demos_in_history:
#             for entry in demo_history:
#                 if entry["role"] != "system":
#                     entry["is_demo"] = True
#                     self._append_history(entry)
#         else:
#             demo_history = [entry for entry in demo_history if entry["role"] != "system"]
#             demo_message = "\n".join([entry["content"] for entry in demo_history])
#             assert self.templates.demonstration_template is not None
#             demonstration = Template(self.templates.demonstration_template).render(demonstration=demo_message)
#             self._append_history(
#                 {
#                     "agent": self.name,
#                     "content": demonstration,
#                     "is_demo": True,
#                     "role": "user",
#                     "message_type": "demonstration",
#                 },
#             )

#     def _get_format_dict(self, **kwargs) -> dict[str, Any]:
#         assert self._problem_statement is not None
#         assert self._env is not None
#         return dict(
#             command_docs=self.tools.config.command_docs,
#             **self.tools.config.env_variables,
#             **kwargs,
#             problem_statement=self._problem_statement.get_problem_statement(),
#             repo=self._env.repo.repo_name if self._env.repo is not None else "",
#             **self._problem_statement.get_extra_fields(),
#         )

#     def _add_templated_messages_to_history(
#         self, templates: list[str], tool_call_ids: list[str] | None = None, **kwargs: str | int | None
#     ) -> None:
#         # TIMING: prompt construction for observation templates
#         detailed = get_detailed_timing_tracker()
#         pc_key = detailed.start_entry("prompt_construction", detail="observation template rendering")

#         messages = []
#         format_dict = self._get_format_dict(**kwargs)
#         for template in templates:
#             try:
#                 messages.append(Template(template).render(**format_dict))
#             except KeyError:
#                 self.logger.debug("The following keys are available: %s", format_dict.keys())
#                 raise

#         detailed.end_entry(pc_key, "prompt_construction")

#         message = "\n".join(messages)
#         self.logger.info(f"🤖 MODEL INPUT\n{message}", extra={"highlighter": None})
#         history_item: dict[str, Any] = {
#             "role": "user",
#             "content": message,
#             "agent": self.name,
#             "message_type": "observation",
#         }
#         if tool_call_ids:
#             assert len(tool_call_ids) == 1, "This should be ensured by the FunctionCalling parse method"
#             history_item["role"] = "tool"
#             history_item["tool_call_ids"] = tool_call_ids
#         self._append_history(history_item)

#     def add_step_to_history(self, step: StepOutput) -> None:
#         self._append_history(
#             {
#                 "role": "assistant",
#                 "content": step.output,
#                 "thought": step.thought,
#                 "action": step.action,
#                 "agent": self.name,
#                 "tool_calls": step.tool_calls,
#                 "message_type": "action",
#                 "thinking_blocks": step.thinking_blocks,
#             },
#         )
#         elided_chars = 0
#         if step.observation.strip() == "":
#             templates = [self.templates.next_step_no_output_template]
#         elif len(step.observation) > self.templates.max_observation_length:
#             templates = [self.templates.next_step_truncated_observation_template]
#             elided_chars = len(step.observation) - self.templates.max_observation_length
#         else:
#             templates = [self.templates.next_step_template]
#         self._add_templated_messages_to_history(
#             templates,
#             observation=step.observation,
#             elided_chars=elided_chars,
#             max_observation_length=self.templates.max_observation_length,
#             tool_call_ids=step.tool_call_ids,
#             **step.state,
#         )

#     def add_instance_template_to_history(self, state: dict[str, str]) -> None:
#         templates: list[str] = []
#         assert self.history[-1]["role"] == "system" or self.history[-1].get("is_demo", False)
#         templates = [self.templates.instance_template]
#         if self.templates.strategy_template is not None:
#             templates.append(self.templates.strategy_template)
#         self._add_templated_messages_to_history(templates, **state)

#     def get_trajectory_data(self) -> dict[str, Any]:
#         assert self._env is not None
#         attempt_data = copy.deepcopy(
#             {
#                 "trajectory": self.trajectory,
#                 "history": self.history,
#                 "info": self.info,
#             }
#         )
#         attempt_data["replay_config"] = self.replay_config.model_dump_json() if self.replay_config is not None else None
#         attempt_data["environment"] = self._env.name
#         return attempt_data

#     def save_trajectory(self) -> None:
#         data = self.get_trajectory_data()
#         assert self.traj_path is not None
#         self.traj_path.write_text(json.dumps(data, indent=2))

#     def get_model_requery_history(
#         self, error_template: str, *, output: str, **kwargs: str | int | float | bool | None
#     ) -> list[dict[str, str]]:
#         format_dict = {**kwargs, **self._get_format_dict()}
#         error_template = Template(error_template).render(**format_dict)
#         self.logger.warning(f"{error_template}")
#         return self.messages + [
#             {"role": "assistant", "content": output, "agent": self.name, "message_type": "assistant"},
#             {"role": "user", "content": error_template, "agent": self.name, "message_type": "user"},
#         ]

#     def attempt_autosubmission_after_error(self, step: StepOutput) -> StepOutput:
#         self.logger.warning("Attempting autosubmission after error")
#         step = step.model_copy(deep=True)
#         step.done = True
#         assert self._env is not None
#         if not asyncio.run(self._env.deployment.is_alive(timeout=10)):
#             self.logger.error("Runtime is no longer alive")
#             try:
#                 last_trajectory_step = self.trajectory[-1]
#             except IndexError:
#                 self.logger.info("No last trajectory step to extract patch from")
#                 return step
#             if "diff" not in last_trajectory_step["state"]:
#                 self.logger.info("No diff in last trajectory step state, cannot autosubmit")
#                 return step
#             diff = last_trajectory_step["state"]["diff"]
#             self.logger.info("Using diff from last trajectory step to autosubmit")
#             step.submission = diff
#             if step.submission:
#                 step.observation = "Environment died unexpectedly. Exited (autosubmitted)"
#                 step.exit_status = f"submitted ({step.exit_status})"
#             else:
#                 self.logger.info("Diff from last traj step empty.")
#             return step
#         repo_name = "/"
#         if self._env.repo is not None:
#             repo_name = f"/{self._env.repo.repo_name}"
#         submission_command = "git add -A && git diff --cached > /root/model.patch"
#         self.logger.info("Executing submission command %s in %s", submission_command, repo_name)
#         try:
#             self._env.execute_command(submission_command, check=True, cwd=repo_name)
#         except Exception as e:
#             self.logger.error("Failed to execute submission command, got %s", e)
#         step = self.handle_submission(step, observation="", force_submission=True)
#         if step.submission:
#             self.logger.info("Exiting with autosubmission")
#             step.observation = "Exited (autosubmitted)"
#         return step

#     def handle_submission(self, step: StepOutput, *, observation="", force_submission: bool = False) -> StepOutput:
#         step = step.model_copy(deep=True)
#         assert self.tools is not None
#         is_submission = self.tools.check_for_submission_cmd(observation or step.observation)
#         if is_submission or force_submission:
#             assert self._env is not None

#             # TIMING: patch_edit_parsing for reading the patch file
#             detailed = get_detailed_timing_tracker()
#             patch_key = detailed.start_entry("patch_edit_parsing", detail="read /root/model.patch")

#             try:
#                 submission = self._env.read_file("/root/model.patch", encoding="utf-8", errors="backslashreplace")
#             except FileNotFoundError:
#                 self.logger.warning("Submission file not found, no submission was made")
#                 detailed.end_entry(patch_key, "patch_edit_parsing")
#                 return step
#             except Exception as e:
#                 self.logger.exception("Failed to read submission file, got %s", e)
#                 detailed.end_entry(patch_key, "patch_edit_parsing")
#                 return step

#             detailed.end_entry(patch_key, "patch_edit_parsing", extra={"patch_size": len(submission)})

#             if submission.strip() != "":
#                 step.submission = submission
#             else:
#                 step.submission = None
#             step.observation = submission
#             if not step.exit_status:
#                 step.exit_status = "submitted"
#             elif step.submission:
#                 step.exit_status = f"submitted ({step.exit_status})"
#             step.done = True
#             self.logger.info(f"Found submission: {submission}")
#         return step

#     def _get_edited_files_with_context(self, patch: str) -> dict[str, str]:
#         assert self._env is not None
#         try:
#             if self._env.repo is None:
#                 pf = None
#             else:
#                 pf = (
#                     PatchFormatter(
#                         patch,
#                         read_method=lambda path: self._env.read_file(
#                             PurePosixPath("/") / self._env.repo.repo_name / path
#                         ),
#                     )
#                     if patch
#                     else None
#                 )
#         except UnidiffParseError:
#             self.logger.error("Failed to parse patch with unidiff. Some variables will be empty.")
#             pf = None
#         out = {}
#         for context_length in [30, 50, 70]:
#             value = "Empty. No edited files found."
#             if pf is not None:
#                 value = pf.get_files_str(original=False, context_length=context_length)
#             out[f"edited_files{context_length}"] = value
#         return out

#     def handle_action(self, step: StepOutput) -> StepOutput:
#         if self.tools.should_block_action(step.action):
#             raise _BlockedActionError()

#         if step.action.strip() == "exit":
#             self.logger.info("Exiting agent")
#             step.done = True
#             step.observation = "Exited"
#             step.exit_status = "exit_command"
#             assert self._env is not None
#             # TIMING: state retrieval on exit path (original tracker)
#             tracker = get_timing_tracker()
#             state_timer = tracker.start_timer("state_retrieval", "get_state (exit)")
#             # TIMING: diff_computation on exit path (detailed tracker)
#             detailed = get_detailed_timing_tracker()
#             diff_key = detailed.start_entry("diff_computation", detail="get_state (exit)")
#             step.state = self.tools.get_state(env=self._env)
#             tracker.end_timer(state_timer, "state_retrieval")
#             detailed.end_entry(diff_key, "diff_computation")
#             return step

#         assert self._env is not None
#         self._chook.on_action_started(step=step)
#         execution_t0 = time.perf_counter()
#         run_action: str = self.tools.guard_multiline_input(step.action).strip()

#         # Classify for both trackers
#         tracker = get_timing_tracker()
#         detailed = get_detailed_timing_tracker()

#         original_category = _classify_command_original(run_action)
#         detailed_category = _classify_command_detailed(run_action)

#         command_for_log = run_action[:200] + "..." if len(run_action) > 200 else run_action

#         # Start timers
#         timer_key = tracker.start_timer(original_category, command_for_log)
#         detailed_key = detailed.start_entry(detailed_category, detail=command_for_log, extra={"command": run_action})

#         try:
#             step.observation = self._env.communicate(
#                 input=run_action,
#                 timeout=self.tools.config.execution_timeout,
#                 check="raise" if self._always_require_zero_exit_code else "ignore",
#             )
#         except CommandTimeoutError:
#             self._n_consecutive_timeouts += 1
#             if self._n_consecutive_timeouts >= self.tools.config.max_consecutive_execution_timeouts:
#                 msg = "Exiting agent due to too many consecutive execution timeouts"
#                 self.logger.critical(msg)
#                 step.execution_time = time.perf_counter() - execution_t0
#                 self._total_execution_time += step.execution_time
#                 raise
#             try:
#                 self._env.interrupt_session()
#             except Exception as f:
#                 self.logger.exception("Failed to interrupt session after command timeout: %s", f, exc_info=True)
#                 step.execution_time = time.perf_counter() - execution_t0
#                 self._total_execution_time += step.execution_time
#                 raise
#             step.observation = Template(self.templates.command_cancelled_timeout_template).render(
#                 **self._get_format_dict(),
#                 timeout=self.tools.config.execution_timeout,
#                 command=run_action,
#             )
#         else:
#             self._n_consecutive_timeouts = 0
#         finally:
#             tracker.end_timer(timer_key, original_category)
#             detailed.end_entry(detailed_key, detailed_category)

#         step.execution_time = time.perf_counter() - execution_t0
#         self._total_execution_time += step.execution_time
#         self._chook.on_action_executed(step=step)

#         # TIMING: state retrieval after action (original tracker)
#         state_timer = tracker.start_timer("state_retrieval", "get_state (post-action)")
#         # TIMING: diff_computation after action (detailed tracker)
#         diff_key = detailed.start_entry("diff_computation", detail="get_state (post-action)")
#         step.state = self.tools.get_state(env=self._env)
#         tracker.end_timer(state_timer, "state_retrieval")
#         detailed.end_entry(diff_key, "diff_computation")

#         if RETRY_WITH_OUTPUT_TOKEN in step.observation:
#             step.observation = step.observation.replace(RETRY_WITH_OUTPUT_TOKEN, "")
#             raise _RetryWithOutput()
#         elif RETRY_WITHOUT_OUTPUT_TOKEN in step.observation:
#             step.observation = step.observation.replace(RETRY_WITHOUT_OUTPUT_TOKEN, "")
#             raise _RetryWithoutOutput()
#         elif EXIT_FORFEIT_TOKEN in step.observation:
#             raise _ExitForfeit()

#         return self.handle_submission(step)

#     def forward(self, history: list[dict[str, str]]) -> StepOutput:
#         if self._total_execution_time > self.tools.config.total_execution_timeout:
#             raise _TotalExecutionTimeExceeded()

#         step = StepOutput()
#         step.query = copy.deepcopy(history)
#         try:
#             self._chook.on_model_query(messages=history, agent=self.name)

#             # Build prompt string for logging (truncated to avoid huge logs)
#             prompt_for_log = json.dumps(history[-1]["content"][:500] if history else "", ensure_ascii=False)

#             # START TIMING: LLM inference — both trackers
#             tracker = get_timing_tracker()
#             detailed = get_detailed_timing_tracker()

#             model_name = self.model.config.name if hasattr(self.model, 'config') and hasattr(self.model.config, 'name') else 'unknown'
#             llm_command_info = f"LLM call (history_len={len(history)}, model={model_name})"
#             timer_key = tracker.start_timer("llm_inference", llm_command_info)
#             detailed_key = detailed.start_entry(
#                 "llm_generation",
#                 detail=llm_command_info,
#                 extra={"prompt_last_message": prompt_for_log},
#             )

#             try:
#                 if self._action_sampler is not None:
#                     assert self._problem_statement is not None
#                     best = self._action_sampler.get_action(
#                         problem_statement=self._problem_statement,
#                         trajectory=self.trajectory,
#                         history=history,
#                     )
#                     output = best.completion
#                     step.extra_info.update(best.extra_info)
#                 else:
#                     output = self.model.query(history)
#             finally:
#                 tracker.end_timer(timer_key, "llm_inference")
#                 response_for_log = output.get("message", "")[:500] if isinstance(output, dict) else str(output)[:500]
#                 detailed.end_entry(detailed_key, "llm_generation", extra={"response": response_for_log})

#             step.output = output["message"]

#             # TIMING: patch_edit_parsing for action parsing
#             parse_key = detailed.start_entry("patch_edit_parsing", detail="tools.parse_actions()")
#             step.thought, step.action = self.tools.parse_actions(output)
#             detailed.end_entry(parse_key, "patch_edit_parsing")

#             step.thinking_blocks = output.get("thinking_blocks", [])
#             if output.get("tool_calls") is not None:
#                 step.tool_call_ids = [call["id"] for call in output["tool_calls"]]
#                 step.tool_calls = output["tool_calls"]
#             self.logger.info(f"💭 THOUGHT\n{step.thought}\n\n🎬 ACTION\n{step.action.strip()}")
#             self._chook.on_actions_generated(step=step)
#             return self.handle_action(step)
#         except Exception as e:
#             if step.action == step.thought == "":
#                 step.thought = step.output
#             e.step = step
#             raise

#     def forward_with_handling(self, history: list[dict[str, str]]) -> StepOutput:
#         detailed = get_detailed_timing_tracker()

#         def handle_error_with_autosubmission(exit_status: str, message: str) -> StepOutput:
#             self.logger.warning(message)
#             return self.attempt_autosubmission_after_error(
#                 StepOutput(
#                     thought=message,
#                     exit_status=exit_status,
#                     output=message,
#                     done=True,
#                 )
#             )

#         def handle_error_with_retry(exception: Exception, template: str, n_requeries: int) -> list[dict[str, str]]:
#             self.logger.warning("Requerying model after %s (%dth requery)", type(exception).__name__, n_requeries)

#             # Move the last llm_generation entry to retry_backoff
#             retry_count = detailed.get_retry_count()
#             detailed.move_last_entry(
#                 "llm_generation",
#                 "retry_backoff",
#                 rename_detail=f"incorrect llm generation {retry_count + 1}",
#             )

#             step: StepOutput = getattr(exception, "step", StepOutput())
#             self.add_step_to_trajectory(step)
#             exception_message = getattr(exception, "message", "")
#             if not exception_message:
#                 try:
#                     exception_message = exception.args[0]
#                 except (IndexError, AttributeError):
#                     pass
#             return self.get_model_requery_history(
#                 error_template=template,
#                 **step.to_template_format_dict(),
#                 **getattr(exception, "extra_info", {}),
#                 exception_message=exception_message,
#             )

#         n_format_fails = 0
#         while n_format_fails < self.max_requeries:
#             try:
#                 return self.forward(history)

#             except KeyboardInterrupt:
#                 raise
#             except EOFError:
#                 raise

#             except FormatError as e:
#                 n_format_fails += 1
#                 history = handle_error_with_retry(
#                     exception=e, template=self.tools.config.format_error_template, n_requeries=n_format_fails
#                 )
#             except _BlockedActionError as e:
#                 n_format_fails += 1
#                 history = handle_error_with_retry(
#                     exception=e, template=self.tools.config.filter.blocklist_error_template, n_requeries=n_format_fails
#                 )
#             except ContentPolicyViolationError:
#                 self.logger.warning("Content policy violation, trying to resample")
#                 n_format_fails += 1
#                 # Move last LLM entry to retry_backoff
#                 retry_count = detailed.get_retry_count()
#                 detailed.move_last_entry(
#                     "llm_generation",
#                     "retry_backoff",
#                     rename_detail=f"incorrect llm generation {retry_count + 1} (content policy violation)",
#                 )
#                 pass
#             except BashIncorrectSyntaxError as e:
#                 n_format_fails += 1
#                 history = handle_error_with_retry(
#                     exception=e,
#                     template=self.templates.shell_check_error_template,
#                     n_requeries=n_format_fails,
#                 )
#             except _RetryWithOutput as e:
#                 history = handle_error_with_retry(
#                     exception=e,
#                     template=self.templates.next_step_template,
#                     n_requeries=n_format_fails,
#                 )
#             except _RetryWithoutOutput:
#                 # Move last LLM entry to retry_backoff
#                 retry_count = detailed.get_retry_count()
#                 detailed.move_last_entry(
#                     "llm_generation",
#                     "retry_backoff",
#                     rename_detail=f"incorrect llm generation {retry_count + 1} (retry without output)",
#                 )
#                 pass

#             except _ExitForfeit:
#                 self.logger.info("Exiting due to forfeit")
#                 return handle_error_with_autosubmission("exit_forfeit", "Exiting due to forfeit")

#             except _TotalExecutionTimeExceeded:
#                 self.logger.exception("Exiting due to total execution time exceeded", exc_info=True)
#                 return handle_error_with_autosubmission("exit_total_execution_time", "Exit due to total execution time exceeded")

#             except CommandTimeoutError:
#                 self.logger.exception("Exiting due to multiple consecutive command timeouts", exc_info=True)
#                 return handle_error_with_autosubmission("exit_command_timeout", "Exit due to multiple consecutive command timeouts")

#             except ContextWindowExceededError:
#                 return handle_error_with_autosubmission("exit_context", "Exit due to context window")
#             except TotalCostLimitExceededError:
#                 raise
#             except CostLimitExceededError:
#                 return handle_error_with_autosubmission("exit_cost", "Exit due to cost limit")
#             except RetryError as e:
#                 self.logger.exception(f"Exiting due to retry error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission("exit_api", f"Exit due to retry error: {e}")
#             except SwerexException as e:
#                 self.logger.exception(f"Exiting due to environment error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission("exit_environment_error", f"Exit due to environment error: {e}")
#             except RuntimeError as e:
#                 self.logger.exception(f"Exiting due to runtime error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission("exit_error", f"Exit due to runtime error: {e}")
#             except Exception as e:
#                 self.logger.exception(f"Exiting due to unknown error: {e}", exc_info=True)
#                 return handle_error_with_autosubmission("exit_error", f"Exit due to unknown error: {e}")

#         self.logger.exception("Exit due to repeated format/blocklist/bash syntax errors", exc_info=True)
#         return handle_error_with_autosubmission("exit_format", "Exit due to repeated format/blocklist/bash syntax errors")

#     def add_step_to_trajectory(self, step: StepOutput) -> None:
#         trajectory_step = TrajectoryStep(
#             {
#                 "action": step.action,
#                 "observation": step.observation,
#                 "response": step.output,
#                 "thought": step.thought,
#                 "execution_time": step.execution_time,
#                 "state": step.state,
#                 "query": step.query,
#                 "extra_info": step.extra_info,
#             },
#         )
#         self.trajectory.append(trajectory_step)

#     def step(self) -> StepOutput:
#         assert self._env is not None
#         self._chook.on_step_start()
#         n_step = len(self.trajectory) + 1
#         self.logger.info("=" * 25 + f" STEP {n_step} " + "=" * 25)
#         step_output = self.forward_with_handling(self.messages)
#         self.add_step_to_history(step_output)
#         self.info["submission"] = step_output.submission
#         self.info["exit_status"] = step_output.exit_status
#         self.info.update(self._get_edited_files_with_context(patch=step_output.submission or ""))
#         self.info["model_stats"] = self.model.stats.model_dump()
#         self.add_step_to_trajectory(step_output)
#         self._chook.on_step_done(step=step_output, info=self.info)
#         return step_output

#     def run(
#         self,
#         env: SWEEnv,
#         problem_statement: ProblemStatement | ProblemStatementConfig,
#         output_dir: Path = Path("."),
#     ) -> AgentRunResult:
#         self.setup(env=env, problem_statement=problem_statement, output_dir=output_dir)
#         self._chook.on_run_start()
#         step_output = StepOutput()
#         while not step_output.done:
#             step_output = self.step()
#             self.save_trajectory()
#         self._chook.on_run_done(trajectory=self.trajectory, info=self.info)
#         self.logger.info("Trajectory saved to %s", self.traj_path)
#         data = self.get_trajectory_data()
#         return AgentRunResult(info=data["info"], trajectory=data["trajectory"])























from __future__ import annotations

import asyncio
import copy
import json
import litellm
from sweagent.timing_tracker import get_timing_tracker
from sweagent.detailed_timing_tracker import get_detailed_timing_tracker, TEST_COMMAND_PATTERNS, GIT_COMMAND_PATTERNS

import logging
import time
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

import yaml
from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field, model_validator
from simple_parsing.helpers.fields import field
from swerex.exceptions import BashIncorrectSyntaxError, CommandTimeoutError, SwerexException
from tenacity import RetryError
from typing_extensions import Self
from unidiff import UnidiffParseError

from sweagent import __version__, get_agent_commit_hash, get_rex_commit_hash, get_rex_version
from sweagent.agent.action_sampler import AbstractActionSampler, ActionSamplerConfig
from sweagent.agent.history_processors import DefaultHistoryProcessor, HistoryProcessor
from sweagent.agent.hooks.abstract import AbstractAgentHook, CombinedAgentHook
from sweagent.agent.models import (
    AbstractModel,
    HumanModel,
    HumanThoughtModel,
    InstanceStats,
    ModelConfig,
    get_model,
)
from sweagent.agent.problem_statement import ProblemStatement, ProblemStatementConfig
from sweagent.agent.reviewer import (
    ChooserRetryLoop,
    RetryLoopConfig,
    ReviewSubmission,
    ScoreRetryLoop,
    get_retry_loop_from_config,
)
from sweagent.environment.swe_env import SWEEnv
from sweagent.exceptions import (
    ContentPolicyViolationError,
    ContextWindowExceededError,
    CostLimitExceededError,
    FormatError,
    TotalCostLimitExceededError,
)
from sweagent.tools.parsing import (
    ActionOnlyParser,
    ThoughtActionParser,
)
from sweagent.tools.tools import ToolConfig, ToolHandler
from sweagent.types import AgentInfo, AgentRunResult, StepOutput, Trajectory, TrajectoryStep
from sweagent.utils.config import _convert_paths_to_abspath, _strip_abspath_from_dict
from sweagent.utils.jinja_warnings import _warn_probably_wrong_jinja_syntax
from sweagent.utils.log import get_logger
from sweagent.utils.patch_formatter import PatchFormatter

def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _extract_llm_usage(output: dict) -> dict[str, Any]:
    """
    Best-effort extraction of token usage/cost from a model output dict.
    If your backend doesn't provide these, fields will be absent.
    """
    usage = output.get("usage") or output.get("token_usage") or output.get("usage_metadata") or {}
    # Common OpenAI-style keys
    in_tok = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("prompt_tokens_total")
    out_tok = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("completion_tokens_total")
    total_tok = usage.get("total_tokens") or usage.get("total_tokens_total")

    # Some wrappers put tokens on the top-level
    in_tok = in_tok if in_tok is not None else output.get("input_tokens")
    out_tok = out_tok if out_tok is not None else output.get("output_tokens")
    total_tok = total_tok if total_tok is not None else output.get("total_tokens")

    # Some wrappers put cost on the top-level or in usage
    cost = output.get("cost_usd") or output.get("cost") or usage.get("cost_usd") or usage.get("cost")

    result: dict[str, Any] = {}
    if (v := _safe_int(in_tok)) is not None:
        result["input_tokens"] = v
    if (v := _safe_int(out_tok)) is not None:
        result["output_tokens"] = v
    if (v := _safe_int(total_tok)) is not None:
        result["total_tokens"] = v
    # Keep cost as float if possible
    if cost is not None:
        try:
            result["cost_usd"] = float(cost)
        except Exception:
            # leave as string if backend uses non-numeric or "n/a"
            result["cost_usd"] = str(cost)
    return result


def _get_full_prompt_for_log(messages: list[dict[str, Any]]) -> str:
    """Serialize the full messages list for logging in the detailed tracker.
    Truncates individual message content to avoid huge JSON.
    """
    truncated = []
    for msg in messages:
        entry = {"role": msg.get("role", "unknown")}
        content = msg.get("content", "")
        if isinstance(content, str):
            entry["content"] = content[:2000] + ("..." if len(content) > 2000 else "")
        elif isinstance(content, list):
            # Multimodal content - truncate text items
            items = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    items.append({"type": "text", "text": text[:2000] + ("..." if len(text) > 2000 else "")})
                elif isinstance(item, dict) and item.get("type") == "image_url":
                    items.append({"type": "image_url", "image_url": "[image data omitted]"})
                else:
                    items.append(item)
            entry["content"] = items
        else:
            entry["content"] = str(content)[:2000]
        if msg.get("tool_calls"):
            entry["tool_calls"] = msg["tool_calls"]
        truncated.append(entry)
    return json.dumps(truncated, ensure_ascii=False)


def _get_response_for_log(output: dict) -> str:
    """Extract a meaningful response string from the model output dict."""
    parts = []
    message = output.get("message", "")
    if message:
        parts.append(message[:2000] + ("..." if len(message) > 2000 else ""))
    tool_calls = output.get("tool_calls")
    if tool_calls:
        for call in tool_calls:
            func = call.get("function", {})
            name = func.get("name", "unknown")
            args = func.get("arguments", "")
            if isinstance(args, str):
                args_str = args[:500] + ("..." if len(args) > 500 else "")
            else:
                args_str = json.dumps(args, ensure_ascii=False)[:500]
            parts.append(f"[tool_call: {name}({args_str})]")
    thinking = output.get("thinking_blocks")
    if thinking:
        parts.append(f"[thinking: {len(thinking)} blocks]")
    return "\n".join(parts) if parts else "(empty response)"


# ── helper: classify a command for the detailed tracker ──────────────
def _classify_command_detailed(run_action: str) -> str:
    """Return the *detailed* timing category for an action string."""
    parts = run_action.split()
    cmd = parts[0] if parts else ""

    # Test / validation
    action_lower = run_action.lower()
    for pat in TEST_COMMAND_PATTERNS:
        if action_lower.startswith(pat):
            return "test_validation_execution"

    # Git operations (submit handled separately by the caller)
    for pat in GIT_COMMAND_PATTERNS:
        if action_lower.startswith(pat):
            return "git_operations"

    # str_replace_editor sub-commands
    if cmd == "str_replace_editor" and len(parts) > 1:
        sub = parts[1]
        if sub == "view":
            return "repository_scan"
        elif sub == "create":
            return "file_creation"
        elif sub in ("str_replace", "insert", "undo_edit"):
            return "apply_file_changes"
        return "shell_command_execution"

    if cmd == "create":
        return "file_creation"
    if cmd in ("edit",):
        return "apply_file_changes"
    if cmd in ("open", "scroll_down", "scroll_up", "goto", "cat", "head", "tail", "less", "more"):
        return "repository_scan"
    if cmd in ("find_file", "search_dir", "search_file", "grep", "find", "ag", "rg"):
        return "repository_scan"
    if cmd in ("submit",):
        return "git_operations"

    return "shell_command_execution"


# ── helper: classify a command for the original tracker ──────────────
def _classify_command_original(run_action: str) -> str:
    """Return the *original* timing category for an action string."""
    parts = run_action.split()
    cmd = parts[0] if parts else ""

    if cmd == "str_replace_editor" and len(parts) > 1:
        sub = parts[1]
        if sub == "view":
            return "file_views"
        elif sub in ("str_replace", "create", "insert", "undo_edit"):
            return "edit_commands"
        return "other_tools"
    if cmd in ("edit", "create"):
        return "edit_commands"
    if cmd in ("open", "scroll_down", "scroll_up", "goto", "cat", "head", "tail", "less", "more"):
        return "file_views"
    if cmd in ("find_file", "search_dir", "search_file", "grep", "find", "ag", "rg"):
        return "file_searches"
    if cmd in ("submit", "exit", "exit_forfeit"):
        return "context_management"
    return "shell_commands"


class TemplateConfig(BaseModel):
    """This configuration is used to define almost all message templates that are
    formatted by the agent and sent to the LM.
    """

    system_template: str = ""
    instance_template: str = ""
    next_step_template: str = "Observation: {{observation}}"

    next_step_truncated_observation_template: str = (
        "Observation: {{observation[:max_observation_length]}}<response clipped>"
        "<NOTE>Observations should not exceeded {{max_observation_length}} characters. "
        "{{elided_chars}} characters were elided. Please try a different command that produces less output "
        "or use head/tail/grep/redirect the output to a file. Do not use interactive pagers.</NOTE>"
    )

    max_observation_length: int = 100_000

    next_step_no_output_template: str = None  # type: ignore

    strategy_template: str | None = None
    demonstration_template: str | None = None

    demonstrations: list[Path] = field(default_factory=list)

    put_demos_in_history: bool = False

    disable_image_processing: bool = False

    shell_check_error_template: str = (
        "Your bash command contained syntax errors and was NOT executed. "
        "Please fix the syntax errors and try again. This can be the result "
        "of not adhering to the syntax for multi-line commands. Here is the output of `bash -n`:\n"
        "{{bash_stdout}}\n{{bash_stderr}}"
    )

    command_cancelled_timeout_template: str = (
        "The command '{{command}}' was cancelled because it took more than {{timeout}} seconds. "
        "Please try a different command that completes more quickly. "
        "Note: A common source of this error is if the command is interactive or requires user input "
        "(it is impossible to receive user input in the current environment, so the command will never complete)."
    )

    def model_post_init(self, __context):
        self.demonstrations = _convert_paths_to_abspath(self.demonstrations)
        if self.next_step_no_output_template is None:
            self.next_step_no_output_template = self.next_step_template

    @model_validator(mode="after")
    def validate_template_jinja_syntax(self) -> Self:
        template_fields = [field for field in self.model_fields.keys() if field.endswith("_template")]
        for field in template_fields:
            value = getattr(self, field)
            _warn_probably_wrong_jinja_syntax(value)
        return self

    @model_validator(mode="after")
    def warnings(self) -> Self:
        logger = get_logger("swea-config", emoji="🔧")
        if self.put_demos_in_history and self.demonstration_template is not None:
            logger.warning("demonstration_template is ignored when put_demos_in_history is True")
        if not self.system_template or not self.instance_template:
            logger.warning(
                "system_template/instance_template is not set, using empty string. Perhaps you were"
                " overwriting the default config? See https://swe-agent.com/latest/usage/cl_tutorial/"
                " for more information. Note: You can ignore this warning in human mode."
            )
        return self


class DefaultAgentConfig(BaseModel):
    name: str = "main"
    templates: TemplateConfig = Field(default_factory=TemplateConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    history_processors: list[HistoryProcessor] = Field(default_factory=lambda: [DefaultHistoryProcessor()])
    model: ModelConfig = Field(description="Model options.")
    max_requeries: int = 3
    action_sampler: ActionSamplerConfig | None = None
    type: Literal["default"] = "default"
    model_config = ConfigDict(extra="forbid")


class ShellAgentConfig(BaseModel):
    name: str = "main"
    templates: TemplateConfig = Field(default_factory=TemplateConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    history_processors: list[HistoryProcessor] = Field(default_factory=lambda: [DefaultHistoryProcessor()])
    model: ModelConfig = Field(description="Model options.")
    max_requeries: int = 3
    type: Literal["shell"] = "shell"
    model_config = ConfigDict(extra="forbid")


class RetryAgentConfig(BaseModel):
    name: str = "retry_main"
    agent_configs: list[DefaultAgentConfig]
    retry_loop: RetryLoopConfig
    type: Literal["retry"] = "retry"
    model_config = ConfigDict(extra="forbid")


AgentConfig = Annotated[DefaultAgentConfig | RetryAgentConfig | ShellAgentConfig, Field(union_mode="left_to_right")]


class _BlockedActionError(Exception):
    pass


class _RetryWithOutput(Exception):
    pass


class _RetryWithoutOutput(Exception):
    pass


class _ExitForfeit(Exception):
    pass


class _TotalExecutionTimeExceeded(Exception):
    pass


RETRY_WITH_OUTPUT_TOKEN = "###SWE-AGENT-RETRY-WITH-OUTPUT###"
RETRY_WITHOUT_OUTPUT_TOKEN = "###SWE-AGENT-RETRY-WITHOUT-OUTPUT###"
EXIT_FORFEIT_TOKEN = "###SWE-AGENT-EXIT-FORFEIT###"


class AbstractAgent:
    def __init__(self, *args, **kwargs):
        model: AbstractModel
        replay_config: BaseModel | None
        logger: logging.Logger

    @classmethod
    def from_config(cls, config: AgentConfig) -> Self: ...

    def add_hook(self, hook: AbstractAgentHook) -> None: ...

    def get_trajectory_data(self) -> dict[str, Any]: ...

    def step(self) -> StepOutput: ...

    def run(self, *args, **kwargs) -> AgentRunResult: ...


def get_agent_from_config(config: AgentConfig) -> AbstractAgent:
    if config.type == "default":
        return DefaultAgent.from_config(config)
    elif config.type == "retry":
        return RetryAgent.from_config(config)
    elif config.type == "shell":
        from sweagent.agent.extra.shell_agent import ShellAgent
        return ShellAgent.from_config(config)
    else:
        msg = f"Unknown agent type: {config.type}"
        raise ValueError(msg)


class RetryAgent(AbstractAgent):
    def __init__(self, config: RetryAgentConfig):
        self.config = config.model_copy(deep=True)
        self._hooks = []
        self._i_attempt = 0
        self.logger = get_logger("swea-agent", emoji="🤠")
        self._agent: DefaultAgent | None = None
        self._attempt_data: list[dict[str, Any]] = []
        self._total_instance_attempt_stats = InstanceStats()
        self._chook = CombinedAgentHook()
        self._traj_path: Path | None = None
        self._problem_statement: ProblemStatement | None = None
        self._env: SWEEnv | None = None
        self._output_dir: Path | None = None
        self._rloop: ScoreRetryLoop | ChooserRetryLoop | None = None

    @property
    def _total_instance_stats(self) -> InstanceStats:
        assert self._rloop is not None
        return self._total_instance_attempt_stats + self._rloop.review_model_stats

    @classmethod
    def from_config(cls, config: RetryAgentConfig) -> Self:
        return cls(config)

    def add_hook(self, hook: AbstractAgentHook) -> None:
        self._chook.add_hook(hook)
        self._hooks.append(hook)

    def setup(
        self, env: SWEEnv, problem_statement: ProblemStatement | ProblemStatementConfig, output_dir: Path = Path(".")
    ) -> None:
        self._total_instance_attempt_stats = InstanceStats()
        self._problem_statement = problem_statement
        self._traj_path = output_dir / (self._problem_statement.id + ".traj")
        self._env = env
        self._output_dir = output_dir
        self._rloop = get_retry_loop_from_config(self.config.retry_loop, problem_statement=problem_statement)

    def _setup_agent(self) -> AbstractAgent:
        agent_config = self.config.agent_configs[self._i_attempt % len(self.config.agent_configs)].model_copy(deep=True)
        remaining_budget = self.config.retry_loop.cost_limit - self._total_instance_stats.instance_cost
        if remaining_budget < agent_config.model.per_instance_cost_limit:
            self.logger.debug("Setting agent per-attempt cost limit to remaining budget: %s", remaining_budget)
            agent_config.model.per_instance_cost_limit = remaining_budget
        self._agent = DefaultAgent.from_config(agent_config)
        for hook in self._hooks:
            self._agent.add_hook(hook)
        assert self._output_dir is not None
        sub_agent_output_dir = self._output_dir / f"attempt_{self._i_attempt}"
        assert self._problem_statement is not None
        assert self._env is not None
        self._agent.setup(env=self._env, problem_statement=self._problem_statement, output_dir=sub_agent_output_dir)
        return self._agent

    def _next_attempt(self) -> None:
        assert self._env is not None
        self._i_attempt += 1
        self._env.hard_reset()
        self._setup_agent()

    def step(self) -> StepOutput:
        assert self._agent is not None
        if self._total_instance_stats.instance_cost > 1.1 * self.config.retry_loop.cost_limit > 0:
            msg = "Total instance cost exceeded cost limit. Triggering autosubmit."
            self.logger.critical(msg)
            return self._agent.attempt_autosubmission_after_error(step=StepOutput())
        try:
            step = self._agent.step()
        except TotalCostLimitExceededError:
            raise
        except Exception as e:
            msg = "Error in agent step: %s. Triggering autosubmit."
            self.logger.critical(msg, e, exc_info=True)
            step = self._agent.attempt_autosubmission_after_error(step=StepOutput())
        return step

    def _finalize_agent_run(self) -> None:
        assert self._agent is not None
        self._agent.save_trajectory()
        self._attempt_data.append(self._agent.get_trajectory_data())
        self._total_instance_attempt_stats += self._agent.model.stats

    def get_trajectory_data(self, choose: bool) -> dict[str, Any]:
        assert self._rloop is not None
        data = {"attempts": self._attempt_data}
        if choose:
            try:
                best_attempt_idx = self._rloop.get_best()
            except TotalCostLimitExceededError:
                raise
            except Exception as e:
                self.logger.critical(f"Error getting best attempt index: {e}. Setting to 0.", exc_info=True)
                best_attempt_idx = 0
            data |= copy.deepcopy(self._attempt_data[best_attempt_idx])
            data["info"]["best_attempt_idx"] = best_attempt_idx
            data["info"]["rloop_model_stats"] = self._rloop.review_model_stats.model_dump()
            data["info"]["model_stats"] = self._total_instance_stats.model_dump()
            if isinstance(self._rloop, ChooserRetryLoop):
                data["info"]["chooser"] = (
                    self._rloop._chooser_output.model_dump() if self._rloop._chooser_output else {}
                )
        return data

    def save_trajectory(self, choose: bool) -> None:
        data = self.get_trajectory_data(choose=choose)
        assert self._traj_path is not None
        self._traj_path.write_text(json.dumps(data, indent=2))

    def run(
        self,
        env: SWEEnv,
        problem_statement: ProblemStatement | ProblemStatementConfig,
        output_dir: Path = Path("."),
    ) -> AgentRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.setup(env=env, problem_statement=problem_statement, output_dir=output_dir)
        assert self._rloop is not None
        self._chook.on_run_start()
        step_output = StepOutput()
        self._setup_agent()
        assert self._agent is not None
        while not step_output.done:
            step_output = self.step()
            self.save_trajectory(choose=False)
            if step_output.done:
                self._rloop.on_submit(
                    ReviewSubmission(
                        trajectory=self._agent.trajectory,
                        info=self._agent.info,
                        model_stats=self._agent.model.stats,
                    )
                )
                if isinstance(self._rloop, ScoreRetryLoop):
                    self._agent.info["review"] = self._rloop.reviews[-1].model_dump()
                self._finalize_agent_run()
                self.save_trajectory(choose=False)
                if self._rloop.retry():
                    assert self._env is not None
                    self._next_attempt()
                    step_output.done = False
        self.save_trajectory(choose=True)
        self._chook.on_run_done(trajectory=self._agent.trajectory, info=self._agent.info)
        self.logger.info("Trajectory saved to %s", self._traj_path)
        data = self.get_trajectory_data(choose=True)
        return AgentRunResult(info=data["info"], trajectory=data["trajectory"])


class DefaultAgent(AbstractAgent):
    def __init__(
        self,
        *,
        templates: TemplateConfig,
        tools: ToolHandler,
        history_processors: list[HistoryProcessor],
        model: AbstractModel,
        max_requeries: int = 3,
        name: str = "main",
        _catch_errors: bool = True,
        _always_require_zero_exit_code: bool = False,
        action_sampler_config: ActionSamplerConfig | None = None,
    ):
        self._catch_errors = _catch_errors
        self._always_require_zero_exit_code = _always_require_zero_exit_code
        self.name = name
        self.model = model
        self.templates = templates
        self.tools = tools
        if isinstance(self.model, HumanThoughtModel):
            self.tools.config.parse_function = ThoughtActionParser()
        elif isinstance(self.model, HumanModel):
            self.tools.config.parse_function = ActionOnlyParser()
        self.history_processors = history_processors
        self.max_requeries = max_requeries
        self.logger = get_logger("swea-agent", emoji="🤠")
        self._env: SWEEnv | None = None
        self._problem_statement: ProblemStatement | ProblemStatementConfig | None = None
        self.traj_path: Path | None = None
        self.history = []
        self._trajectory = []
        self.info = AgentInfo()
        self._chook = CombinedAgentHook()
        self._replay_config: BaseModel | None = None
        self._action_sampler: AbstractActionSampler | None = None
        if action_sampler_config is not None:
            self._action_sampler = action_sampler_config.get(self.model, self.tools)
        self._n_consecutive_timeouts = 0
        self._total_execution_time = 0.0

    @classmethod
    def from_config(cls, config: DefaultAgentConfig) -> Self:
        config = config.model_copy(deep=True)
        model = get_model(config.model, config.tools)
        return cls(
            templates=config.templates,
            tools=ToolHandler(config.tools),
            history_processors=config.history_processors,
            model=model,
            max_requeries=config.max_requeries,
            action_sampler_config=config.action_sampler,
        )

    def add_hook(self, hook: AbstractAgentHook) -> None:
        hook.on_init(agent=self)
        self._chook.add_hook(hook)

    @property
    def trajectory(self) -> Trajectory:
        return self._trajectory

    @property
    def replay_config(self) -> BaseModel | None:
        return self._replay_config

    @replay_config.setter
    def replay_config(self, value: BaseModel):
        from sweagent.run.run_single import RunSingleConfig
        self._replay_config = RunSingleConfig.model_validate(_strip_abspath_from_dict(value.model_dump()))

    @property
    def messages(self) -> list[dict[str, Any]]:
        # TIMING: context compaction
        detailed = get_detailed_timing_tracker()
        cc_key = detailed.start_entry("context_compaction", detail="history processor chain")

        filtered_history = [entry for entry in self.history if entry["agent"] == self.name]
        messages = filtered_history
        for processor in self.history_processors:
            messages = processor(messages)

        detailed.end_entry(cc_key, "context_compaction")
        return messages

    def _append_history(self, item: dict[str, Any]) -> None:
        self._chook.on_query_message_added(**item)
        self.history.append(item)

    def setup(
        self,
        env: SWEEnv,
        problem_statement: ProblemStatement | ProblemStatementConfig,
        output_dir: Path = Path("."),
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        # TIMING: original tracker - agent setup
        tracker = get_timing_tracker()
        setup_timer_key = tracker.start_timer("agent_setup", "agent.setup()")

        # TIMING: detailed tracker - tool installation goes under process_bootstrap
        detailed = get_detailed_timing_tracker()
        install_key = detailed.start_entry("process_bootstrap", detail="tool installation and environment configuration")

        try:
            if hasattr(problem_statement, "type") and problem_statement.type == "swe_bench_multimodal":
                from sweagent.agent.problem_statement import SWEBenchMultimodalProblemStatement
                if isinstance(problem_statement, SWEBenchMultimodalProblemStatement):
                    if not problem_statement.disable_image_processing and self.templates.disable_image_processing:
                        problem_statement.disable_image_processing = True

            self._problem_statement = problem_statement
            self._env = env
            iid = self._problem_statement.id
            self.logger.info("Setting up agent for instance %s", iid)

            self.traj_path = output_dir / (self._problem_statement.id + ".traj")
            self.logger.info("Trajectory will be saved to %s", self.traj_path)

            self._chook.on_tools_installation_started()
            self.tools.install(self._env)
            self._chook.on_setup_attempt()
            self.info = AgentInfo()
            self.info["swe_agent_hash"] = get_agent_commit_hash()
            self.info["swe_agent_version"] = __version__
            self.info["swe_rex_version"] = get_rex_version()
            self.info["swe_rex_hash"] = get_rex_commit_hash()
            assert self._env is not None
            assert self._problem_statement is not None
            self._env.set_env_variables({"PROBLEM_STATEMENT": self._problem_statement.get_problem_statement_for_env()})

            # End tool installation timing, start prompt construction timing
            detailed.end_entry(install_key, "process_bootstrap")

            prompt_key = detailed.start_entry("prompt_construction", detail="system/instance prompt construction")
            self.add_system_message_to_history()
            self.add_demonstrations_to_history()
            self.add_instance_template_to_history(state=self.tools.get_state(self._env))
            detailed.end_entry(prompt_key, "prompt_construction")

            self._chook.on_setup_done()
        finally:
            tracker.end_timer(setup_timer_key, "agent_setup")

    def add_system_message_to_history(self) -> None:
        assert self._problem_statement is not None
        system_msg = Template(self.templates.system_template).render(**self._get_format_dict())
        self.logger.info(f"SYSTEM ({self.name})\n{system_msg}")
        self._append_history(
            {"role": "system", "content": system_msg, "agent": self.name, "message_type": "system_prompt"}
        )

    def add_demonstrations_to_history(self) -> None:
        for demonstration_path in self.templates.demonstrations:
            self._add_demonstration_to_history(demonstration_path)

    def _add_demonstration_to_history(self, demonstration_path: Path) -> None:
        if self.templates.demonstration_template is None and not self.templates.put_demos_in_history:
            msg = "Cannot use demonstrations without a demonstration template or put_demos_in_history=True"
            raise ValueError(msg)
        self.logger.info(f"DEMONSTRATION: {demonstration_path}")
        _demo_text = Path(demonstration_path).read_text()
        if demonstration_path.suffix == ".yaml":
            demo_history = yaml.safe_load(_demo_text)["history"]
        else:
            demo_history = json.loads(_demo_text)["history"]
        if self.templates.put_demos_in_history:
            for entry in demo_history:
                if entry["role"] != "system":
                    entry["is_demo"] = True
                    self._append_history(entry)
        else:
            demo_history = [entry for entry in demo_history if entry["role"] != "system"]
            demo_message = "\n".join([entry["content"] for entry in demo_history])
            assert self.templates.demonstration_template is not None
            demonstration = Template(self.templates.demonstration_template).render(demonstration=demo_message)
            self._append_history(
                {
                    "agent": self.name,
                    "content": demonstration,
                    "is_demo": True,
                    "role": "user",
                    "message_type": "demonstration",
                },
            )

    def _get_format_dict(self, **kwargs) -> dict[str, Any]:
        assert self._problem_statement is not None
        assert self._env is not None
        return dict(
            command_docs=self.tools.config.command_docs,
            **self.tools.config.env_variables,
            **kwargs,
            problem_statement=self._problem_statement.get_problem_statement(),
            repo=self._env.repo.repo_name if self._env.repo is not None else "",
            **self._problem_statement.get_extra_fields(),
        )

    def _add_templated_messages_to_history(
        self, templates: list[str], tool_call_ids: list[str] | None = None, **kwargs: str | int | None
    ) -> None:
        messages = []
        format_dict = self._get_format_dict(**kwargs)
        for template in templates:
            try:
                messages.append(Template(template).render(**format_dict))
            except KeyError:
                self.logger.debug("The following keys are available: %s", format_dict.keys())
                raise

        message = "\n".join(messages)
        self.logger.info(f"🤖 MODEL INPUT\n{message}", extra={"highlighter": None})
        history_item: dict[str, Any] = {
            "role": "user",
            "content": message,
            "agent": self.name,
            "message_type": "observation",
        }
        if tool_call_ids:
            assert len(tool_call_ids) == 1
            history_item["role"] = "tool"
            history_item["tool_call_ids"] = tool_call_ids
        self._append_history(history_item)

    def add_step_to_history(self, step: StepOutput) -> None:
        self._append_history(
            {
                "role": "assistant",
                "content": step.output,
                "thought": step.thought,
                "action": step.action,
                "agent": self.name,
                "tool_calls": step.tool_calls,
                "message_type": "action",
                "thinking_blocks": step.thinking_blocks,
            },
        )
        elided_chars = 0
        if step.observation.strip() == "":
            templates = [self.templates.next_step_no_output_template]
        elif len(step.observation) > self.templates.max_observation_length:
            templates = [self.templates.next_step_truncated_observation_template]
            elided_chars = len(step.observation) - self.templates.max_observation_length
        else:
            templates = [self.templates.next_step_template]

        # TIMING: prompt construction for observation template
        detailed = get_detailed_timing_tracker()
        pc_key = detailed.start_entry("prompt_construction", detail="observation template rendering")
        self._add_templated_messages_to_history(
            templates,
            observation=step.observation,
            elided_chars=elided_chars,
            max_observation_length=self.templates.max_observation_length,
            tool_call_ids=step.tool_call_ids,
            **step.state,
        )
        detailed.end_entry(pc_key, "prompt_construction")

    def add_instance_template_to_history(self, state: dict[str, str]) -> None:
        templates: list[str] = []
        assert self.history[-1]["role"] == "system" or self.history[-1].get("is_demo", False)
        templates = [self.templates.instance_template]
        if self.templates.strategy_template is not None:
            templates.append(self.templates.strategy_template)
        self._add_templated_messages_to_history(templates, **state)

    def get_trajectory_data(self) -> dict[str, Any]:
        assert self._env is not None
        attempt_data = copy.deepcopy(
            {
                "trajectory": self.trajectory,
                "history": self.history,
                "info": self.info,
            }
        )
        attempt_data["replay_config"] = self.replay_config.model_dump_json() if self.replay_config is not None else None
        attempt_data["environment"] = self._env.name
        return attempt_data

    def save_trajectory(self) -> None:
        data = self.get_trajectory_data()
        assert self.traj_path is not None
        self.traj_path.write_text(json.dumps(data, indent=2))

    def get_model_requery_history(
        self, error_template: str, *, output: str, **kwargs: str | int | float | bool | None
    ) -> list[dict[str, str]]:
        format_dict = {**kwargs, **self._get_format_dict()}
        error_template = Template(error_template).render(**format_dict)
        self.logger.warning(f"{error_template}")
        return self.messages + [
            {"role": "assistant", "content": output, "agent": self.name, "message_type": "assistant"},
            {"role": "user", "content": error_template, "agent": self.name, "message_type": "user"},
        ]

    def attempt_autosubmission_after_error(self, step: StepOutput) -> StepOutput:
        self.logger.warning("Attempting autosubmission after error")
        step = step.model_copy(deep=True)
        step.done = True
        assert self._env is not None
        if not asyncio.run(self._env.deployment.is_alive(timeout=10)):
            self.logger.error("Runtime is no longer alive")
            try:
                last_trajectory_step = self.trajectory[-1]
            except IndexError:
                self.logger.info("No last trajectory step to extract patch from")
                return step
            if "diff" not in last_trajectory_step["state"]:
                self.logger.info("No diff in last trajectory step state, cannot autosubmit")
                return step
            diff = last_trajectory_step["state"]["diff"]
            self.logger.info("Using diff from last trajectory step to autosubmit")
            step.submission = diff
            if step.submission:
                step.observation = "Environment died unexpectedly. Exited (autosubmitted)"
                step.exit_status = f"submitted ({step.exit_status})"
            else:
                self.logger.info("Diff from last traj step empty.")
            return step
        repo_name = "/"
        if self._env.repo is not None:
            repo_name = f"/{self._env.repo.repo_name}"
        submission_command = "git add -A && git diff --cached > /root/model.patch"
        self.logger.info("Executing submission command %s in %s", submission_command, repo_name)
        try:
            self._env.execute_command(submission_command, check=True, cwd=repo_name)
        except Exception as e:
            self.logger.error("Failed to execute submission command, got %s", e)
        step = self.handle_submission(step, observation="", force_submission=True)
        if step.submission:
            self.logger.info("Exiting with autosubmission")
            step.observation = "Exited (autosubmitted)"
        return step

    def handle_submission(self, step: StepOutput, *, observation="", force_submission: bool = False) -> StepOutput:
        step = step.model_copy(deep=True)
        assert self.tools is not None
        is_submission = self.tools.check_for_submission_cmd(observation or step.observation)
        if is_submission or force_submission:
            assert self._env is not None
            try:
                submission = self._env.read_file("/root/model.patch", encoding="utf-8", errors="backslashreplace")
            except FileNotFoundError:
                self.logger.warning("Submission file not found, no submission was made")
                return step
            except Exception as e:
                self.logger.exception("Failed to read submission file, got %s", e)
                return step

            if submission.strip() != "":
                step.submission = submission
            else:
                step.submission = None
            step.observation = submission
            if not step.exit_status:
                step.exit_status = "submitted"
            elif step.submission:
                step.exit_status = f"submitted ({step.exit_status})"
            step.done = True
            self.logger.info(f"Found submission: {submission}")
        return step

    def _get_edited_files_with_context(self, patch: str) -> dict[str, str]:
        assert self._env is not None
        try:
            if self._env.repo is None:
                pf = None
            else:
                pf = (
                    PatchFormatter(
                        patch,
                        read_method=lambda path: self._env.read_file(
                            PurePosixPath("/") / self._env.repo.repo_name / path
                        ),
                    )
                    if patch
                    else None
                )
        except UnidiffParseError:
            self.logger.error("Failed to parse patch with unidiff. Some variables will be empty.")
            pf = None
        out = {}
        for context_length in [30, 50, 70]:
            value = "Empty. No edited files found."
            if pf is not None:
                value = pf.get_files_str(original=False, context_length=context_length)
            out[f"edited_files{context_length}"] = value
        return out

    def handle_action(self, step: StepOutput) -> StepOutput:
        if self.tools.should_block_action(step.action):
            raise _BlockedActionError()

        if step.action.strip() == "exit":
            self.logger.info("Exiting agent")
            step.done = True
            step.observation = "Exited"
            step.exit_status = "exit_command"
            assert self._env is not None
            tracker = get_timing_tracker()
            state_timer = tracker.start_timer("state_retrieval", "get_state (exit)")
            detailed = get_detailed_timing_tracker()
            diff_key = detailed.start_entry("diff_computation", detail="get_state (exit)")
            step.state = self.tools.get_state(env=self._env)
            tracker.end_timer(state_timer, "state_retrieval")
            detailed.end_entry(diff_key, "diff_computation")
            return step

        assert self._env is not None
        self._chook.on_action_started(step=step)
        execution_t0 = time.perf_counter()
        run_action: str = self.tools.guard_multiline_input(step.action).strip()

        # Classify for both trackers
        tracker = get_timing_tracker()
        detailed = get_detailed_timing_tracker()

        original_category = _classify_command_original(run_action)
        detailed_category = _classify_command_detailed(run_action)

        command_for_log = run_action[:200] + "..." if len(run_action) > 200 else run_action

        # Start timers
        timer_key = tracker.start_timer(original_category, command_for_log)
        detailed_key = detailed.start_entry(detailed_category, detail=command_for_log, extra={"command": run_action})

        try:
            step.observation = self._env.communicate(
                input=run_action,
                timeout=self.tools.config.execution_timeout,
                check="raise" if self._always_require_zero_exit_code else "ignore",
            )
        except CommandTimeoutError:
            self._n_consecutive_timeouts += 1
            if self._n_consecutive_timeouts >= self.tools.config.max_consecutive_execution_timeouts:
                msg = "Exiting agent due to too many consecutive execution timeouts"
                self.logger.critical(msg)
                step.execution_time = time.perf_counter() - execution_t0
                self._total_execution_time += step.execution_time
                raise
            try:
                self._env.interrupt_session()
            except Exception as f:
                self.logger.exception("Failed to interrupt session after command timeout: %s", f, exc_info=True)
                step.execution_time = time.perf_counter() - execution_t0
                self._total_execution_time += step.execution_time
                raise
            step.observation = Template(self.templates.command_cancelled_timeout_template).render(
                **self._get_format_dict(),
                timeout=self.tools.config.execution_timeout,
                command=run_action,
            )
        else:
            self._n_consecutive_timeouts = 0
        finally:
            tracker.end_timer(timer_key, original_category)
            detailed.end_entry(detailed_key, detailed_category)

        step.execution_time = time.perf_counter() - execution_t0
        self._total_execution_time += step.execution_time
        self._chook.on_action_executed(step=step)

        # State retrieval / diff computation after action
        state_timer = tracker.start_timer("state_retrieval", "get_state (post-action)")
        diff_key = detailed.start_entry("diff_computation", detail="get_state (post-action)")
        step.state = self.tools.get_state(env=self._env)
        tracker.end_timer(state_timer, "state_retrieval")
        detailed.end_entry(diff_key, "diff_computation")

        if RETRY_WITH_OUTPUT_TOKEN in step.observation:
            step.observation = step.observation.replace(RETRY_WITH_OUTPUT_TOKEN, "")
            raise _RetryWithOutput()
        elif RETRY_WITHOUT_OUTPUT_TOKEN in step.observation:
            step.observation = step.observation.replace(RETRY_WITHOUT_OUTPUT_TOKEN, "")
            raise _RetryWithoutOutput()
        elif EXIT_FORFEIT_TOKEN in step.observation:
            raise _ExitForfeit()

        return self.handle_submission(step)

    def forward(self, history: list[dict[str, str]]) -> StepOutput:
        if self._total_execution_time > self.tools.config.total_execution_timeout:
            raise _TotalExecutionTimeExceeded()

        step = StepOutput()
        step.query = copy.deepcopy(history)
        try:
            self._chook.on_model_query(messages=history, agent=self.name)

            # Build full prompt for logging
            full_prompt = _get_full_prompt_for_log(history)

            # START TIMING: LLM inference — both trackers
            tracker = get_timing_tracker()
            detailed = get_detailed_timing_tracker()

            model_name = self.model.config.name if hasattr(self.model, 'config') and hasattr(self.model.config, 'name') else 'unknown'
            llm_command_info = f"LLM call (history_len={len(history)}, model={model_name})"
            timer_key = tracker.start_timer("llm_inference", llm_command_info)
            detailed_key = detailed.start_entry(
                "llm_generation",
                detail=llm_command_info,
                extra={"prompt": full_prompt},
            )

            # Snapshot model stats before the query to compute per-call token/cost delta
            _stats_sent_before = self.model.stats.tokens_sent if hasattr(self.model, "stats") else 0
            _stats_received_before = self.model.stats.tokens_received if hasattr(self.model, "stats") else 0
            _stats_cost_before = self.model.stats.instance_cost if hasattr(self.model, "stats") else 0.0

            try:
                if self._action_sampler is not None:
                    assert self._problem_statement is not None
                    best = self._action_sampler.get_action(
                        problem_statement=self._problem_statement,
                        trajectory=self.trajectory,
                        history=history,
                    )
                    output = best.completion
                    step.extra_info.update(best.extra_info)
                else:
                    output = self.model.query(history)
            finally:
                tracker.end_timer(timer_key, "llm_inference")
                # Capture response - handle case where output might not be set on exception
                try:
                    response_for_log = _get_response_for_log(output)
                except NameError:
                    response_for_log = "(query failed - no output)"
                # Compute per-call token/cost deltas from model stats
                if hasattr(self.model, "stats"):
                    call_input = self.model.stats.tokens_sent - _stats_sent_before
                    call_output = self.model.stats.tokens_received - _stats_received_before
                    # model.stats.tokens_received only counts message.content tokens.
                    # When the model responds with only a tool call, content is empty → 0 tokens.
                    # Count tool call argument tokens separately for the timing profile.
                    try:
                        if isinstance(output, dict) and output.get("tool_calls"):
                            _model_name = (
                                self.model.config.name
                                if hasattr(self.model, "config") and hasattr(self.model.config, "name")
                                else "unknown"
                            )
                            for _tc in output["tool_calls"]:
                                if isinstance(_tc, dict):
                                    _func = _tc.get("function", {})
                                    _tc_text = (_func.get("name", "") + " " + _func.get("arguments", "")).strip()
                                    if _tc_text:
                                        call_output += litellm.utils.token_counter(
                                            text=_tc_text, model=_model_name
                                        )
                    except Exception:
                        pass
                    call_cost = self.model.stats.instance_cost - _stats_cost_before
                    usage_extra: dict = {
                        "input_tokens": call_input,
                        "output_tokens": call_output,
                        "total_tokens": call_input + call_output,
                        "cost_usd": round(call_cost, 6),
                    }
                else:
                    try:
                        usage_extra = _extract_llm_usage(output) if isinstance(output, dict) else {}
                    except Exception:
                        usage_extra = {}

                detailed.end_entry(
                    detailed_key,
                    "llm_generation",
                    extra={
                        "response": response_for_log,
                        **usage_extra,
                    },
                )

            step.output = output["message"]
            step.thought, step.action = self.tools.parse_actions(output)
            step.thinking_blocks = output.get("thinking_blocks", [])
            if output.get("tool_calls") is not None:
                step.tool_call_ids = [call["id"] for call in output["tool_calls"]]
                step.tool_calls = output["tool_calls"]
            self.logger.info(f"💭 THOUGHT\n{step.thought}\n\n🎬 ACTION\n{step.action.strip()}")
            self._chook.on_actions_generated(step=step)
            return self.handle_action(step)
        except Exception as e:
            if step.action == step.thought == "":
                step.thought = step.output
            e.step = step
            raise

    def forward_with_handling(self, history: list[dict[str, str]]) -> StepOutput:
        detailed = get_detailed_timing_tracker()

        def handle_error_with_autosubmission(exit_status: str, message: str) -> StepOutput:
            self.logger.warning(message)
            return self.attempt_autosubmission_after_error(
                StepOutput(
                    thought=message,
                    exit_status=exit_status,
                    output=message,
                    done=True,
                )
            )

        # def handle_error_with_retry_and_reclassify(exception: Exception, template: str, n_requeries: int) -> list[dict[str, str]]:
        #     """Handle errors caused by bad LLM output: reclassify the LLM call as retry_backoff."""
        #     self.logger.warning("Requerying model after %s (%dth requery)", type(exception).__name__, n_requeries)

        #     # Move the last llm_generation entry to retry_backoff — this was a bad LLM output
        #     retry_count = detailed.get_retry_count()
        #     detailed.move_last_entry(
        #         "llm_generation",
        #         "retry_backoff",
        #         rename_detail=f"incorrect llm generation {retry_count + 1}",
        #     )

        #     step: StepOutput = getattr(exception, "step", StepOutput())
        #     self.add_step_to_trajectory(step)
        #     exception_message = getattr(exception, "message", "")
        #     if not exception_message:
        #         try:
        #             exception_message = exception.args[0]
        #         except (IndexError, AttributeError):
        #             pass
        #     return self.get_model_requery_history(
        #         error_template=template,
        #         **step.to_template_format_dict(),
        #         **getattr(exception, "extra_info", {}),
        #         exception_message=exception_message,
        #     )

        def handle_error_with_retry_and_reclassify(exception: Exception, template: str, n_requeries: int) -> list[dict[str, str]]:
            """Handle errors caused by bad LLM output: reclassify the LLM call as retry_backoff."""
            self.logger.warning("Requerying model after %s (%dth requery)", type(exception).__name__, n_requeries)

            # Move the last llm_generation entry to retry_backoff — this was a bad LLM output
            retry_count = detailed.get_retry_count()
            error_type = type(exception).__name__
            exception_message = getattr(exception, "message", "")
            if not exception_message:
                try:
                    exception_message = exception.args[0]
                except (IndexError, AttributeError):
                    exception_message = ""
            detailed.move_last_entry(
                "llm_generation",
                "retry_backoff",
                rename_detail=f"incorrect llm generation {retry_count + 1}",
                extra_update={"error_type": error_type, "error_message": str(exception_message)[:500]},
            )

            step: StepOutput = getattr(exception, "step", StepOutput())
            self.add_step_to_trajectory(step)
            return self.get_model_requery_history(
                error_template=template,
                **step.to_template_format_dict(),
                **getattr(exception, "extra_info", {}),
                exception_message=exception_message,
            )

        def handle_error_with_retry_no_reclassify(exception: Exception, template: str, n_requeries: int) -> list[dict[str, str]]:
            """Handle errors NOT caused by bad LLM output: keep the LLM call as llm_generation."""
            self.logger.warning("Requerying model after %s (%dth requery)", type(exception).__name__, n_requeries)

            step: StepOutput = getattr(exception, "step", StepOutput())
            self.add_step_to_trajectory(step)
            exception_message = getattr(exception, "message", "")
            if not exception_message:
                try:
                    exception_message = exception.args[0]
                except (IndexError, AttributeError):
                    pass
            return self.get_model_requery_history(
                error_template=template,
                **step.to_template_format_dict(),
                **getattr(exception, "extra_info", {}),
                exception_message=exception_message,
            )

        n_format_fails = 0
        while n_format_fails < self.max_requeries:
            try:
                return self.forward(history)

            except KeyboardInterrupt:
                raise
            except EOFError:
                raise

            # Errors caused by bad LLM output — reclassify to retry_backoff
            except FormatError as e:
                n_format_fails += 1
                history = handle_error_with_retry_and_reclassify(
                    exception=e, template=self.tools.config.format_error_template, n_requeries=n_format_fails
                )
            except _BlockedActionError as e:
                n_format_fails += 1
                history = handle_error_with_retry_and_reclassify(
                    exception=e, template=self.tools.config.filter.blocklist_error_template, n_requeries=n_format_fails
                )
            # except ContentPolicyViolationError:
            #     self.logger.warning("Content policy violation, trying to resample")
            #     n_format_fails += 1
            #     # Reclassify: content policy = bad LLM output
            #     retry_count = detailed.get_retry_count()
            #     detailed.move_last_entry(
            #         "llm_generation",
            #         "retry_backoff",
            #         rename_detail=f"incorrect llm generation {retry_count + 1} (content policy violation)",
            #     )
            #     pass
            except ContentPolicyViolationError:
                self.logger.warning("Content policy violation, trying to resample")
                n_format_fails += 1
                retry_count = detailed.get_retry_count()
                detailed.move_last_entry(
                    "llm_generation",
                    "retry_backoff",
                    rename_detail=f"incorrect llm generation {retry_count + 1} (content policy violation)",
                    extra_update={"error_type": "ContentPolicyViolationError", "error_message": "Content policy violation"},
                )
                pass
            except BashIncorrectSyntaxError as e:
                n_format_fails += 1
                history = handle_error_with_retry_and_reclassify(
                    exception=e,
                    template=self.templates.shell_check_error_template,
                    n_requeries=n_format_fails,
                )

            # Errors NOT caused by bad LLM output — keep as llm_generation
            except _RetryWithOutput as e:
                history = handle_error_with_retry_no_reclassify(
                    exception=e,
                    template=self.templates.next_step_template,
                    n_requeries=n_format_fails,
                )
            except _RetryWithoutOutput:
                # Environment-triggered retry, not bad LLM output — don't reclassify
                pass

            # Errors that cause exit
            except _ExitForfeit:
                self.logger.info("Exiting due to forfeit")
                return handle_error_with_autosubmission("exit_forfeit", "Exiting due to forfeit")

            except _TotalExecutionTimeExceeded:
                self.logger.exception("Exiting due to total execution time exceeded", exc_info=True)
                return handle_error_with_autosubmission("exit_total_execution_time", "Exit due to total execution time exceeded")

            except CommandTimeoutError:
                self.logger.exception("Exiting due to multiple consecutive command timeouts", exc_info=True)
                return handle_error_with_autosubmission("exit_command_timeout", "Exit due to multiple consecutive command timeouts")

            except ContextWindowExceededError:
                return handle_error_with_autosubmission("exit_context", "Exit due to context window")
            except TotalCostLimitExceededError:
                raise
            except CostLimitExceededError:
                return handle_error_with_autosubmission("exit_cost", "Exit due to cost limit")
            except RetryError as e:
                self.logger.exception(f"Exiting due to retry error: {e}", exc_info=True)
                return handle_error_with_autosubmission("exit_api", f"Exit due to retry error: {e}")
            except SwerexException as e:
                self.logger.exception(f"Exiting due to environment error: {e}", exc_info=True)
                return handle_error_with_autosubmission("exit_environment_error", f"Exit due to environment error: {e}")
            except RuntimeError as e:
                self.logger.exception(f"Exiting due to runtime error: {e}", exc_info=True)
                return handle_error_with_autosubmission("exit_error", f"Exit due to runtime error: {e}")
            except Exception as e:
                self.logger.exception(f"Exiting due to unknown error: {e}", exc_info=True)
                return handle_error_with_autosubmission("exit_error", f"Exit due to unknown error: {e}")

        self.logger.exception("Exit due to repeated format/blocklist/bash syntax errors", exc_info=True)
        return handle_error_with_autosubmission("exit_format", "Exit due to repeated format/blocklist/bash syntax errors")

    def add_step_to_trajectory(self, step: StepOutput) -> None:
        trajectory_step = TrajectoryStep(
            {
                "action": step.action,
                "observation": step.observation,
                "response": step.output,
                "thought": step.thought,
                "execution_time": step.execution_time,
                "state": step.state,
                "query": step.query,
                "extra_info": step.extra_info,
            },
        )
        self.trajectory.append(trajectory_step)

    def step(self) -> StepOutput:
        assert self._env is not None
        self._chook.on_step_start()
        n_step = len(self.trajectory) + 1
        self.logger.info("=" * 25 + f" STEP {n_step} " + "=" * 25)
        step_output = self.forward_with_handling(self.messages)
        self.add_step_to_history(step_output)
        self.info["submission"] = step_output.submission
        self.info["exit_status"] = step_output.exit_status
        self.info.update(self._get_edited_files_with_context(patch=step_output.submission or ""))
        self.info["model_stats"] = self.model.stats.model_dump()
        self.add_step_to_trajectory(step_output)
        self._chook.on_step_done(step=step_output, info=self.info)
        return step_output

    def run(
        self,
        env: SWEEnv,
        problem_statement: ProblemStatement | ProblemStatementConfig,
        output_dir: Path = Path("."),
    ) -> AgentRunResult:
        self.setup(env=env, problem_statement=problem_statement, output_dir=output_dir)
        self._chook.on_run_start()
        step_output = StepOutput()
        while not step_output.done:
            step_output = self.step()
            self.save_trajectory()
        self._chook.on_run_done(trajectory=self.trajectory, info=self.info)
        self.logger.info("Trajectory saved to %s", self.traj_path)
        data = self.get_trajectory_data()
        return AgentRunResult(info=data["info"], trajectory=data["trajectory"])