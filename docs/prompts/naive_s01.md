# Naive generator: exact request for s01 (include_descriptions=on)

Request parameters (besides system/messages): {"max_tokens": 16000, "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}

No temperature/top_p/top_k are sent (API default).

## system[0]  cache_control=None

````text
You write Cedar authorization policies for an AI agent that calls MCP tools.
Below are the Cedar schema the policies must validate against and the MCP tool manifests (tools/list responses) of the servers the agent can call.
The user message is the administrator's intent.
````

## system[1]  cache_control=None

````text
## Cedar schema
```cedarschema
namespace AOB {
  type approve_workorderInput = {
    site_id: String,
    wonum: String
  };

  type assign_technicianInput = {
    craft?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    hours_planned?: AOB::Number,
    labor_code: String,
    site_id: String,
    start_date?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    wonum: String
  };

  type cancel_workorderInput = {
    reason?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    site_id: String,
    wonum: String
  };

  type close_workorderInput = {
    actual_hours?: AOB::Number,
    failure_code?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    resolution_notes?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    site_id: String,
    wonum: String
  };

  type generate_work_orderInput = {
    aob_source?: {
      typeChoice0?: AOB::generate_work_order::Input::aob_source::TypeChoice0,
      typeChoice1?: AOB::Null
    },
    asset_num: String,
    description: String,
    location?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    notes?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    priority?: Long,
    reported_by?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    site_id: String,
    wonum?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    work_type?: String
  };

  type get_failure_codesInput = {
    code?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    }
  };

  type get_my_assigned_workordersInput = {
    labor_code: String,
    open_only?: Bool,
    site_id?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    }
  };

  type get_schedule_calendarInput = {
    date_from?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    date_to?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    group_by?: String,
    site_id: String
  };

  type get_workorderInput = {
    site_id: String,
    wonum: String
  };

  type get_workorder_actuals_vs_plannedInput = {
    site_id: String,
    wonum: String
  };

  type get_workorder_costsInput = {
    site_id: String,
    wonum: String
  };

  type get_workorder_kpisInput = {
    period_months?: Long,
    site_id: String
  };

  type get_workorder_tasksInput = {
    site_id: String,
    wonum: String
  };

  type list_workordersInput = {
    asset_num?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    date_from?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    date_to?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    page_num?: Long,
    page_size?: Long,
    priority?: {
      typeChoice0?: Long,
      typeChoice1?: AOB::Null
    },
    site_id?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    status?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    }
  };

  type update_workorderInput = {
    asset_num?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    description?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    failure_code?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    location?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    notes?: {
      typeChoice0?: String,
      typeChoice1?: AOB::Null
    },
    priority?: {
      typeChoice0?: Long,
      typeChoice1?: AOB::Null
    },
    site_id: String,
    wonum: String
  };

  entity McpServer;

  entity Null;

  entity Number;

  entity User;

  action "approve_workorder" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: approve_workorderInput
    }
  };

  action "assign_technician" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: assign_technicianInput
    }
  };

  action "cancel_workorder" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: cancel_workorderInput
    }
  };

  action "close_workorder" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      approval?: PGI::Approval,
      input: close_workorderInput
    }
  };

  action "generate_work_order" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: generate_work_orderInput
    }
  };

  action "get_failure_codes" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_failure_codesInput
    }
  };

  action "get_my_assigned_workorders" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_my_assigned_workordersInput
    }
  };

  action "get_schedule_calendar" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_schedule_calendarInput
    }
  };

  action "get_workorder" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_workorderInput
    }
  };

  action "get_workorder_actuals_vs_planned" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_workorder_actuals_vs_plannedInput
    }
  };

  action "get_workorder_costs" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_workorder_costsInput
    }
  };

  action "get_workorder_kpis" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_workorder_kpisInput
    }
  };

  action "get_workorder_tasks" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: get_workorder_tasksInput
    }
  };

  action "list_workorders" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: list_workordersInput
    }
  };

  action "update_workorder" appliesTo {
    principal: [User],
    resource: [McpServer],
    context: {
      input: update_workorderInput
    }
  };
}

namespace PGI {
  @pgi_action("AOB::close_workorder")
  @pgi_context_attribute("approval")
  type Approval = {
    approver: AOB::User,
    status: String,
    wonum: String
  };
}

namespace AOB::generate_work_order::Input::aob_source {
  entity TypeChoice0;
}

```
````

## system[2]  cache_control={'type': 'ephemeral'}

````text
## MCP tool manifests
### MCP server `wo`
```json
{
  "tools": [
    {
      "description": "List work orders with optional filters (site, status, asset, priority, dates).\n    status accepts OPEN / APPROVED_PENDING; page_size=0 returns all matches in one call.",
      "inputSchema": {
        "properties": {
          "asset_num": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Asset Num"
          },
          "date_from": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Date From"
          },
          "date_to": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Date To"
          },
          "page_num": {
            "default": 1,
            "title": "Page Num",
            "type": "integer"
          },
          "page_size": {
            "default": 50,
            "title": "Page Size",
            "type": "integer"
          },
          "priority": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Priority"
          },
          "site_id": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Site Id"
          },
          "status": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Status"
          }
        },
        "title": "list_workordersArguments",
        "type": "object"
      },
      "name": "list_workorders",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrdersResult": {
            "properties": {
              "labor_code": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Labor Code"
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "site_id": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Site Id"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "total": {
                "title": "Total",
                "type": "integer"
              },
              "work_orders": {
                "items": {
                  "$ref": "#/$defs/WorkOrderItem"
                },
                "title": "Work Orders",
                "type": "array"
              }
            },
            "required": [
              "total",
              "work_orders",
              "message"
            ],
            "title": "WorkOrdersResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrdersResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "list_workordersOutput",
        "type": "object"
      },
      "title": "List Work Orders"
    },
    {
      "description": "Get a single work order by number and site.",
      "inputSchema": {
        "properties": {
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "get_workorderArguments",
        "type": "object"
      },
      "name": "get_workorder",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_workorderOutput",
        "type": "object"
      },
      "title": "Get Work Order"
    },
    {
      "description": "List the child tasks of a parent work order.",
      "inputSchema": {
        "properties": {
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "get_workorder_tasksArguments",
        "type": "object"
      },
      "name": "get_workorder_tasks",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "TasksResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "parent_wonum": {
                "title": "Parent Wonum",
                "type": "string"
              },
              "site_id": {
                "title": "Site Id",
                "type": "string"
              },
              "tasks": {
                "items": {
                  "$ref": "#/$defs/WorkOrderItem"
                },
                "title": "Tasks",
                "type": "array"
              },
              "total": {
                "title": "Total",
                "type": "integer"
              }
            },
            "required": [
              "parent_wonum",
              "site_id",
              "total",
              "tasks",
              "message"
            ],
            "title": "TasksResult",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/TasksResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_workorder_tasksOutput",
        "type": "object"
      },
      "title": "Get Work Order Tasks"
    },
    {
      "description": "Actual labor/material/service/tool cost breakdown for a work order.",
      "inputSchema": {
        "properties": {
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "get_workorder_costsArguments",
        "type": "object"
      },
      "name": "get_workorder_costs",
      "outputSchema": {
        "$defs": {
          "CostBreakdownEntry": {
            "properties": {
              "amount": {
                "title": "Amount",
                "type": "number"
              },
              "category": {
                "title": "Category",
                "type": "string"
              },
              "share_pct": {
                "title": "Share Pct",
                "type": "number"
              }
            },
            "required": [
              "category",
              "amount",
              "share_pct"
            ],
            "title": "CostBreakdownEntry",
            "type": "object"
          },
          "CostsResult": {
            "additionalProperties": true,
            "properties": {
              "actual_hours": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actual Hours"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "breakdown": {
                "default": [],
                "items": {
                  "$ref": "#/$defs/CostBreakdownEntry"
                },
                "title": "Breakdown",
                "type": "array"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "site_id": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Site Id"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "total_cost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Total Cost"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              }
            },
            "required": [
              "message"
            ],
            "title": "CostsResult",
            "type": "object"
          },
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/CostsResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_workorder_costsOutput",
        "type": "object"
      },
      "title": "Get Work Order Costs"
    },
    {
      "description": "Estimated vs actual hours and cost variance for a work order.",
      "inputSchema": {
        "properties": {
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "get_workorder_actuals_vs_plannedArguments",
        "type": "object"
      },
      "name": "get_workorder_actuals_vs_planned",
      "outputSchema": {
        "$defs": {
          "ActualsVsPlannedResult": {
            "additionalProperties": true,
            "properties": {
              "labor_cost": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VarianceEntry"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null
              },
              "labor_hours": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VarianceEntry"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null
              },
              "material_cost": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VarianceEntry"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "service_cost": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VarianceEntry"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null
              },
              "site_id": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Site Id"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "tool_cost": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VarianceEntry"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null
              },
              "total_cost": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VarianceEntry"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              }
            },
            "required": [
              "message"
            ],
            "title": "ActualsVsPlannedResult",
            "type": "object"
          },
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "VarianceEntry": {
            "properties": {
              "actual": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actual"
              },
              "estimated": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estimated"
              },
              "over_budget": {
                "anyOf": [
                  {
                    "type": "boolean"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Over Budget"
              },
              "variance_abs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Variance Abs"
              },
              "variance_pct": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Variance Pct"
              }
            },
            "title": "VarianceEntry",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/ActualsVsPlannedResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_workorder_actuals_vs_plannedOutput",
        "type": "object"
      },
      "title": "Get Work Order Actuals vs Planned"
    },
    {
      "description": "Site KPIs: totals, backlog, overdue, avg completion, priority/asset breakdowns.",
      "inputSchema": {
        "properties": {
          "period_months": {
            "default": 3,
            "title": "Period Months",
            "type": "integer"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          }
        },
        "required": [
          "site_id"
        ],
        "title": "get_workorder_kpisArguments",
        "type": "object"
      },
      "name": "get_workorder_kpis",
      "outputSchema": {
        "$defs": {
          "AssetCount": {
            "properties": {
              "asset": {
                "title": "Asset",
                "type": "string"
              },
              "count": {
                "title": "Count",
                "type": "integer"
              }
            },
            "required": [
              "asset",
              "count"
            ],
            "title": "AssetCount",
            "type": "object"
          },
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "KpiResult": {
            "additionalProperties": true,
            "properties": {
              "avg_completion_hrs": {
                "title": "Avg Completion Hrs",
                "type": "number"
              },
              "backlog": {
                "title": "Backlog",
                "type": "integer"
              },
              "completed": {
                "title": "Completed",
                "type": "integer"
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "overdue": {
                "title": "Overdue",
                "type": "integer"
              },
              "period_months": {
                "title": "Period Months",
                "type": "integer"
              },
              "priority_breakdown": {
                "additionalProperties": {
                  "type": "integer"
                },
                "default": {},
                "title": "Priority Breakdown",
                "type": "object"
              },
              "site_id": {
                "title": "Site Id",
                "type": "string"
              },
              "top_assets_by_wo_count": {
                "default": [],
                "items": {
                  "$ref": "#/$defs/AssetCount"
                },
                "title": "Top Assets By Wo Count",
                "type": "array"
              },
              "total_workorders": {
                "title": "Total Workorders",
                "type": "integer"
              }
            },
            "required": [
              "site_id",
              "period_months",
              "total_workorders",
              "completed",
              "backlog",
              "overdue",
              "avg_completion_hrs",
              "message"
            ],
            "title": "KpiResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/KpiResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_workorder_kpisOutput",
        "type": "object"
      },
      "title": "Get Work Order KPIs"
    },
    {
      "description": "Scheduled (non-terminal) work orders in a date window, bucketed by day.",
      "inputSchema": {
        "properties": {
          "date_from": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Date From"
          },
          "date_to": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Date To"
          },
          "group_by": {
            "default": "date",
            "title": "Group By",
            "type": "string"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          }
        },
        "required": [
          "site_id"
        ],
        "title": "get_schedule_calendarArguments",
        "type": "object"
      },
      "name": "get_schedule_calendar",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "ScheduleDay": {
            "properties": {
              "count": {
                "title": "Count",
                "type": "integer"
              },
              "date": {
                "title": "Date",
                "type": "string"
              },
              "workorders": {
                "items": {
                  "$ref": "#/$defs/WorkOrderItem"
                },
                "title": "Workorders",
                "type": "array"
              }
            },
            "required": [
              "date",
              "count",
              "workorders"
            ],
            "title": "ScheduleDay",
            "type": "object"
          },
          "ScheduleResult": {
            "additionalProperties": true,
            "properties": {
              "by_date": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/ScheduleDay"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "By Date"
              },
              "date_from": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Date From"
              },
              "date_to": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Date To"
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "site_id": {
                "title": "Site Id",
                "type": "string"
              },
              "total_scheduled": {
                "title": "Total Scheduled",
                "type": "integer"
              },
              "workorders": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/WorkOrderItem"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Workorders"
              }
            },
            "required": [
              "site_id",
              "total_scheduled",
              "message"
            ],
            "title": "ScheduleResult",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/ScheduleResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_schedule_calendarOutput",
        "type": "object"
      },
      "title": "Get Schedule Calendar"
    },
    {
      "description": "Work orders assigned to a given technician (labor code).",
      "inputSchema": {
        "properties": {
          "labor_code": {
            "title": "Labor Code",
            "type": "string"
          },
          "open_only": {
            "default": true,
            "title": "Open Only",
            "type": "boolean"
          },
          "site_id": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Site Id"
          }
        },
        "required": [
          "labor_code"
        ],
        "title": "get_my_assigned_workordersArguments",
        "type": "object"
      },
      "name": "get_my_assigned_workorders",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrdersResult": {
            "properties": {
              "labor_code": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Labor Code"
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "site_id": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Site Id"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "total": {
                "title": "Total",
                "type": "integer"
              },
              "work_orders": {
                "items": {
                  "$ref": "#/$defs/WorkOrderItem"
                },
                "title": "Work Orders",
                "type": "array"
              }
            },
            "required": [
              "total",
              "work_orders",
              "message"
            ],
            "title": "WorkOrdersResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrdersResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_my_assigned_workordersOutput",
        "type": "object"
      },
      "title": "Get My Assigned Work Orders"
    },
    {
      "annotations": {
        "destructiveHint": false,
        "idempotentHint": true,
        "openWorldHint": true,
        "readOnlyHint": true
      },
      "description": "Read the FCC failure-code reference catalog from CouchDB.\n\n    Omit ``code`` to list all available failure codes, or pass an exact code\n    such as ``FC001``. Matching is case-insensitive and CouchDB metadata is not\n    returned.\n    ",
      "inputSchema": {
        "properties": {
          "code": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Code"
          }
        },
        "title": "get_failure_codesArguments",
        "type": "object"
      },
      "name": "get_failure_codes",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "FailureCodeItem": {
            "properties": {
              "code": {
                "title": "Code",
                "type": "string"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              }
            },
            "required": [
              "code"
            ],
            "title": "FailureCodeItem",
            "type": "object"
          },
          "FailureCodesResult": {
            "properties": {
              "code": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Code"
              },
              "failure_codes": {
                "items": {
                  "$ref": "#/$defs/FailureCodeItem"
                },
                "title": "Failure Codes",
                "type": "array"
              },
              "message": {
                "title": "Message",
                "type": "string"
              },
              "total": {
                "title": "Total",
                "type": "integer"
              }
            },
            "required": [
              "total",
              "failure_codes",
              "message"
            ],
            "title": "FailureCodesResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/FailureCodesResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "get_failure_codesOutput",
        "type": "object"
      },
      "title": "Get Failure Codes"
    },
    {
      "description": "Create a work order (status WAPPR). Attach aob_source provenance (agent/trigger/evidence).",
      "inputSchema": {
        "properties": {
          "aob_source": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Aob Source"
          },
          "asset_num": {
            "title": "Asset Num",
            "type": "string"
          },
          "description": {
            "title": "Description",
            "type": "string"
          },
          "location": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Location"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Notes"
          },
          "priority": {
            "default": 3,
            "title": "Priority",
            "type": "integer"
          },
          "reported_by": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Reported By"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Wonum"
          },
          "work_type": {
            "default": "CM",
            "title": "Work Type",
            "type": "string"
          }
        },
        "required": [
          "description",
          "asset_num",
          "site_id"
        ],
        "title": "generate_work_orderArguments",
        "type": "object"
      },
      "name": "generate_work_order",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderMutationResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderMutationResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderMutationResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "generate_work_orderOutput",
        "type": "object"
      },
      "title": "Generate Work Order"
    },
    {
      "description": "Update mutable fields on a work order.",
      "inputSchema": {
        "properties": {
          "asset_num": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Asset Num"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Description"
          },
          "failure_code": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Failure Code"
          },
          "location": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Location"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Notes"
          },
          "priority": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Priority"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "update_workorderArguments",
        "type": "object"
      },
      "name": "update_workorder",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderMutationResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderMutationResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderMutationResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "update_workorderOutput",
        "type": "object"
      },
      "title": "Update Work Order"
    },
    {
      "description": "Approve a work order (-> APPR).",
      "inputSchema": {
        "properties": {
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "approve_workorderArguments",
        "type": "object"
      },
      "name": "approve_workorder",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderMutationResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderMutationResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderMutationResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "approve_workorderOutput",
        "type": "object"
      },
      "title": "Approve Work Order"
    },
    {
      "description": "Assign a technician (adds a wplabor line).",
      "inputSchema": {
        "properties": {
          "craft": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Craft"
          },
          "hours_planned": {
            "default": 8.0,
            "title": "Hours Planned",
            "type": "number"
          },
          "labor_code": {
            "title": "Labor Code",
            "type": "string"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "start_date": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Start Date"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id",
          "labor_code"
        ],
        "title": "assign_technicianArguments",
        "type": "object"
      },
      "name": "assign_technician",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderMutationResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderMutationResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderMutationResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "assign_technicianOutput",
        "type": "object"
      },
      "title": "Assign Technician"
    },
    {
      "description": "Close a work order (-> COMP) with actuals and resolution.",
      "inputSchema": {
        "properties": {
          "actual_hours": {
            "default": 0.0,
            "title": "Actual Hours",
            "type": "number"
          },
          "failure_code": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Failure Code"
          },
          "resolution_notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Resolution Notes"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "close_workorderArguments",
        "type": "object"
      },
      "name": "close_workorder",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderMutationResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderMutationResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderMutationResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "close_workorderOutput",
        "type": "object"
      },
      "title": "Close Work Order"
    },
    {
      "description": "Cancel a work order (-> CAN).",
      "inputSchema": {
        "properties": {
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Reason"
          },
          "site_id": {
            "title": "Site Id",
            "type": "string"
          },
          "wonum": {
            "title": "Wonum",
            "type": "string"
          }
        },
        "required": [
          "wonum",
          "site_id"
        ],
        "title": "cancel_workorderArguments",
        "type": "object"
      },
      "name": "cancel_workorder",
      "outputSchema": {
        "$defs": {
          "ErrorResult": {
            "properties": {
              "error": {
                "title": "Error",
                "type": "string"
              }
            },
            "required": [
              "error"
            ],
            "title": "ErrorResult",
            "type": "object"
          },
          "LaborLine": {
            "additionalProperties": true,
            "properties": {
              "craft": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Craft"
              },
              "laborcode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborcode"
              },
              "laborhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Laborhrs"
              },
              "startdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Startdate"
              }
            },
            "title": "LaborLine",
            "type": "object"
          },
          "WorkOrderItem": {
            "additionalProperties": true,
            "properties": {
              "actfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actfinish"
              },
              "actlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabcost"
              },
              "actlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actlabhrs"
              },
              "actmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actmatcost"
              },
              "actservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actservcost"
              },
              "actstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Actstart"
              },
              "acttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttoolcost"
              },
              "acttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Acttotalcost"
              },
              "aob_asset_class": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Asset Class"
              },
              "aob_source": {
                "anyOf": [
                  {
                    "additionalProperties": true,
                    "type": "object"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Aob Source"
              },
              "assetnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Assetnum"
              },
              "description": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description"
              },
              "description_longdescription": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Description Longdescription"
              },
              "estatapprtotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estatapprtotalcost"
              },
              "estlabcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabcost"
              },
              "estlabhrs": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estlabhrs"
              },
              "estmatcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estmatcost"
              },
              "estservcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Estservcost"
              },
              "esttoolcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttoolcost"
              },
              "esttotalcost": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Esttotalcost"
              },
              "failurecode": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Failurecode"
              },
              "jpnum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Jpnum"
              },
              "lead": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Lead"
              },
              "location": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Location"
              },
              "orgid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Orgid"
              },
              "parent": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Parent"
              },
              "reportdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportdate"
              },
              "reportedby": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Reportedby"
              },
              "schedfinish": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedfinish"
              },
              "schedstart": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Schedstart"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "status_date": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status Date"
              },
              "targcompdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targcompdate"
              },
              "targstartdate": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Targstartdate"
              },
              "taskid": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Taskid"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "wopriority": {
                "anyOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wopriority"
              },
              "worktype": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Worktype"
              },
              "wplabor": {
                "anyOf": [
                  {
                    "items": {
                      "$ref": "#/$defs/LaborLine"
                    },
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wplabor"
              }
            },
            "title": "WorkOrderItem",
            "type": "object"
          },
          "WorkOrderMutationResult": {
            "properties": {
              "message": {
                "title": "Message",
                "type": "string"
              },
              "siteid": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Siteid"
              },
              "status": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Status"
              },
              "wonum": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": null,
                "title": "Wonum"
              },
              "work_order": {
                "$ref": "#/$defs/WorkOrderItem"
              }
            },
            "required": [
              "work_order",
              "message"
            ],
            "title": "WorkOrderMutationResult",
            "type": "object"
          }
        },
        "properties": {
          "result": {
            "anyOf": [
              {
                "$ref": "#/$defs/WorkOrderMutationResult"
              },
              {
                "$ref": "#/$defs/ErrorResult"
              }
            ],
            "title": "Result"
          }
        },
        "required": [
          "result"
        ],
        "title": "cancel_workorderOutput",
        "type": "object"
      },
      "title": "Cancel Work Order"
    }
  ]
}
```
````

## messages[0]  role=user

````text
# Close work orders only after a real approval

Our maintenance agent may close work orders at the MAIN site, but only when a person has properly approved the job first.

- It may close a work order only at MAIN.
- Before closing, there must be an approval on record, and it must be a granted approval, not one still waiting.
- The approval has to be for that same work order. An approval for a different job does not count.
- The agent can never approve its own work. The approval must come from someone other than the agent.
- The agent may also list MAIN's work orders so it can find what to close. It must say it is looking at MAIN; it may not list every site at once.
- It must not approve work orders itself, and nothing else is granted.

Output only Cedar policies.
````
