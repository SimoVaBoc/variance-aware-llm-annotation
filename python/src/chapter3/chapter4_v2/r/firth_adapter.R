# Thin adapter: Firth logistic regression with R logistf, exactly as specified.
#
# Usage: Rscript --vanilla firth_adapter.R <input.json> <output.json>
#
# The design is built in Python and arrives as numbers; no factor coding, level
# ordering or row filtering happens here. Every double travels as a hexadecimal
# string ("%a"), so nothing is rounded in either direction. The adapter fits,
# records what logistf reports and judges nothing: convergence certification,
# usability and every status are decided in Python against the specification.
#
# Per fit: logistf(firth = TRUE, flic = FALSE, pl = TRUE, plconf = LABEL only,
# init = zeros, control = logistf.control(...), plcontrol = logistpl.control(...)),
# na.action = na.fail. The model matrix R builds must be identical to the one
# Python sent; otherwise the fit is refused.

suppressPackageStartupMessages({
  library(jsonlite)
  library(logistf)
})

args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2)
input <- fromJSON(args[1], simplifyVector = FALSE)

hex <- function(x) sprintf("%a", as.numeric(x))
num <- function(v) as.numeric(unlist(v))

ctl <- input$control
plc <- input$profile_control
control <- logistf.control(maxit = as.integer(ctl$maxit), maxhs = as.integer(ctl$maxhs),
                           maxstep = num(ctl$maxstep), lconv = num(ctl$lconv),
                           gconv = num(ctl$gconv), xconv = num(ctl$xconv),
                           collapse = isTRUE(ctl$collapse), fit = ctl$fit)
plcontrol <- logistpl.control(maxit = as.integer(plc$maxit), maxhs = as.integer(plc$maxhs),
                              maxstep = num(plc$maxstep), lconv = num(plc$lconv),
                              xconv = num(plc$xconv), ortho = isTRUE(plc$ortho),
                              pr = isTRUE(plc$pr))

y <- as.integer(unlist(input$y))
n <- length(y)
z_names <- unlist(input$control_columns)
Z <- matrix(num(input$controls_hex), nrow = n, byrow = TRUE)
colnames(Z) <- if (length(z_names)) paste0("z", seq_along(z_names)) else character(0)

fit_one <- function(spec) {
  label <- as.integer(unlist(spec$label))
  d <- data.frame(y = y, LABEL = label)
  if (ncol(Z)) d <- cbind(d, as.data.frame(Z))
  rhs <- paste(c("LABEL", colnames(Z)), collapse = " + ")
  formula <- as.formula(paste("y ~", rhs))
  sent <- unname(cbind(1, label, Z))
  built <- unname(model.matrix(formula, data = d))
  identical_design <- identical(dim(sent), dim(built)) && all(sent == built)
  warnings <- character(0)
  out <- list(name = spec$name, design_identical = identical_design, warnings = warnings)
  if (!identical_design) {
    out$status <- "refused"
    out$error <- "the model matrix built in R differs from the design sent"
    return(out)
  }
  k <- ncol(sent)
  fit <- tryCatch(
    withCallingHandlers(
      logistf(formula, data = d, pl = TRUE, alpha = 1 - num(plc$level), firth = TRUE,
              flic = FALSE, init = rep(0, k), plconf = 2L, control = control,
              plcontrol = plcontrol, na.action = na.fail),
      warning = function(w) {
        warnings <<- c(warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }),
    error = function(e) e)
  out$warnings <- warnings
  if (inherits(fit, "error")) {
    out$status <- "error"
    out$error <- conditionMessage(fit)
    return(out)
  }
  label_row <- which(rownames(fit$pl.conv) == "2")
  out$status <- "fitted"
  out$n <- fit$n
  out$coefficient_names <- c("(Intercept)", "LABEL", z_names)
  out$coefficients_hex <- hex(fit$coefficients)
  out$var_hex <- hex(as.vector(t(fit$var)))
  out$conv_hex <- list(loglik_change = hex(fit$conv[1]), max_abs_score = hex(fit$conv[2]),
                       beta_change = hex(fit$conv[3]))
  out$iter <- list(full = unname(fit$iter[["full"]]), null = unname(fit$iter[["null"]]))
  out$label_ci_hex <- list(lower = hex(fit$ci.lower[2]), upper = hex(fit$ci.upper[2]))
  out$label_pl_conv_hex <- if (length(label_row) == 1) {
    row <- fit$pl.conv[label_row, ]
    list(lower_loglik = hex(row[1]), lower_beta = hex(row[2]),
         upper_loglik = hex(row[3]), upper_beta = hex(row[4]))
  } else NULL
  out$label_pl_iter <- list(lower = unname(fit$pl.iter[2, "Lower"]),
                            upper = unname(fit$pl.iter[2, "Upper"]))
  out$method <- fit$method
  out$method_ci <- fit$method.ci
  out$firth <- isTRUE(fit$firth)
  out$flic <- isTRUE(fit$flic)
  out$control_echo <- fit$control[c("maxit", "maxhs", "maxstep", "lconv", "gconv", "xconv",
                                    "collapse", "fit")]
  out
}

session <- function() {
  installed <- installed.packages()
  deps <- tools::package_dependencies("logistf", db = installed, recursive = TRUE,
                                      which = c("Depends", "Imports", "LinkingTo"))[[1]]
  wanted <- sort(unique(c("logistf", "jsonlite", deps)))
  wanted <- wanted[wanted %in% rownames(installed)]
  info <- sessionInfo()
  loaded <- c(info$otherPkgs, info$loadedOnly)
  list(
    r_version = R.version.string,
    platform = R.version$platform,
    running_under = info$running,
    logistf_built = packageDescription("logistf")$Built,
    installed_dependency_versions = as.list(setNames(installed[wanted, "Version"], wanted)),
    loaded_package_versions = lapply(loaded[order(names(loaded))], function(p) p$Version)
  )
}

result <- list(
  r_version = R.version.string,
  logistf_version = as.character(packageVersion("logistf")),
  jsonlite_version = as.character(packageVersion("jsonlite")),
  platform = R.version$platform,
  session = session(),
  fits = lapply(input$fits, fit_one)
)
write_json(result, args[2], auto_unbox = TRUE, null = "null", digits = NA)
