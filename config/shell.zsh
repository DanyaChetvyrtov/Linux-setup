# Loaded after existing Zsh customizations.
path=("$HOME/.local/bin" $path)
typeset -U path
if (( $+commands[direnv] )); then
  eval "$(direnv hook zsh)"
fi
if (( $+commands[nvim] )); then
  export EDITOR=nvim VISUAL=nvim
fi
if (( $+commands[fdfind] )) && ! (( $+commands[fd] )); then
  alias fd=fdfind
fi
# Select the development JDK without changing system Java alternatives.
if [[ -d /usr/lib/jvm/java-21-openjdk-amd64 ]]; then
  export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
  path=("$JAVA_HOME/bin" $path)
fi
